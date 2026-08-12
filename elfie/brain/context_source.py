"""Brain-owned bounded context state for one continuous Elfie."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Callable, Deque, Mapping, Optional, Tuple

from elfie.brain.context_types import (
    ConversationContext,
    ConversationMessage,
    EffectiveCapabilities,
    EmotionSnapshot,
    MemoryContext,
    MemoryItem,
)
from elfie.brain.memory import MemorySystem
from elfie.brain.perception_types import SocialPayload, TurnFrame
from elfie.message_types import EventId, UTCDateTime

CapabilityReader = Callable[
    [UTCDateTime, Mapping[str, Tuple[str, ...]]], EffectiveCapabilities
]


class BrainContextState:
    """Read bounded context and capabilities under Brain ownership."""

    def __init__(
        self,
        *,
        memory: MemorySystem,
        capability_reader: CapabilityReader,
        clock: Callable[[], UTCDateTime],
        history_capacity: int = 32,
        event_identity_capacity: int = 2048,
        conversations_per_channel: int = 128,
    ) -> None:
        self._memory = memory
        self._capability_reader = capability_reader
        self._clock = clock
        self._history_capacity = history_capacity
        self._histories: dict[tuple[str, str], Deque[ConversationMessage]] = {}
        self._event_identity_capacity = event_identity_capacity
        self._conversations_per_channel = conversations_per_channel
        self._seen_conversation_events: set[EventId] = set()
        self._seen_conversation_order: Deque[EventId] = deque()
        self._recorded_owner_events: set[EventId] = set()
        self._recorded_owner_order: Deque[EventId] = deque()
        self._authorized_conversations: dict[str, Deque[str]] = {}
        self._lock = Lock()

    def conversation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
    ) -> ConversationContext:
        """Append only the admitted conversation and return its bounded history."""
        conversation_ids: list[str] = []
        active_key: Optional[tuple[str, str]] = None
        with self._lock:
            for event in frame.events:
                payload = event.payload
                if not isinstance(payload, SocialPayload):
                    continue
                conversation_ids.append(payload.conversation_id)
                active_key = (payload.channel_id, payload.conversation_id)
                self._remember_conversation(payload.channel_id, payload.conversation_id)
                if event.meta.event_id not in self._seen_conversation_events:
                    history = self._histories.setdefault(
                        active_key,
                        deque(maxlen=self._history_capacity),
                    )
                    history.append(
                        ConversationMessage(
                            event_id=event.meta.event_id,
                            sender=payload.sender,
                            occurred_at=event.meta.occurred_at,
                            content=payload.content,
                        )
                    )
                    self._remember_seen_event(event.meta.event_id)
            history = (
                tuple(self._histories.get(active_key, ()))
                if active_key is not None
                else ()
            )
        unique_conversations = tuple(dict.fromkeys(conversation_ids))
        return ConversationContext(
            revision=frame.revision,
            captured_at=captured_at,
            conversation_id=(
                unique_conversations[0] if len(unique_conversations) == 1 else None
            ),
            messages=history,
        )

    def memory(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> MemoryContext:
        """Record owner text once and retrieve one bounded memory excerpt."""
        query_parts: list[str] = []
        source_ids: list[EventId] = []
        dominant = emotion.dominant or "calm"
        intensity = max((value.intensity for value in emotion.values), default=0.0)
        for event in frame.events:
            payload = event.payload
            if not isinstance(payload, SocialPayload):
                continue
            query_parts.append(payload.content)
            source_ids.append(event.meta.event_id)
            if (
                payload.sender.source_kind == "owner"
                and event.meta.event_id not in self._recorded_owner_events
            ):
                self._memory.record_episode(
                    content=f"主人对我说: '{payload.content}'。",
                    emotion=dominant,
                    intensity=intensity * 100.0,
                    stimulus=f"owner:{event.meta.event_id}",
                )
                self._remember_recorded_owner_event(event.meta.event_id)
        if not query_parts:
            return MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                items=(),
            )
        content = self._memory.get_context(
            query="\n".join(query_parts),
            emotion=dominant,
            intensity=intensity * 100.0,
            current_time=captured_at.isoformat(),
            top_k=5,
        ).strip()
        items = (
            (
                MemoryItem(
                    memory_id=EventId(f"memory-context:{frame.frame_id}"),
                    content=content,
                    relevance=1.0,
                    source_event_ids=tuple(source_ids),
                ),
            )
            if content
            else ()
        )
        return MemoryContext(
            revision=frame.revision,
            captured_at=captured_at,
            items=items,
        )

    def capabilities(self, captured_at: UTCDateTime) -> EffectiveCapabilities:
        """Read a sibling-free capability projection through the injected reader."""
        with self._lock:
            authorized = {
                channel_id: tuple(conversations)
                for channel_id, conversations in self._authorized_conversations.items()
            }
        return self._capability_reader(captured_at, authorized)

    def current(self) -> EffectiveCapabilities:
        """Return a fresh capability snapshot for decision validation."""
        return self.capabilities(self._clock())

    def _remember_seen_event(self, event_id: EventId) -> None:
        self._seen_conversation_events.add(event_id)
        self._seen_conversation_order.append(event_id)
        while len(self._seen_conversation_order) > self._event_identity_capacity:
            self._seen_conversation_events.discard(
                self._seen_conversation_order.popleft()
            )

    def _remember_recorded_owner_event(self, event_id: EventId) -> None:
        self._recorded_owner_events.add(event_id)
        self._recorded_owner_order.append(event_id)
        while len(self._recorded_owner_order) > self._event_identity_capacity:
            self._recorded_owner_events.discard(self._recorded_owner_order.popleft())

    def _remember_conversation(self, channel_id: str, conversation_id: str) -> None:
        conversations = self._authorized_conversations.setdefault(channel_id, deque())
        if conversation_id in conversations:
            return
        conversations.append(conversation_id)
        while len(conversations) > self._conversations_per_channel:
            conversations.popleft()


__all__ = ("BrainContextState", "CapabilityReader")
