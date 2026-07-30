"""Coordinator-owned context reads for one complete Elfie."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Callable, Deque, Optional, Tuple

from elfie.body.port import BodyPort
from elfie.brain.context_types import (
    BodyCapabilityDescriptor,
    ConnectedChannelDescriptor,
    ConversationContext,
    ConversationMessage,
    EffectiveCapabilities,
    EmotionSnapshot,
    MemoryContext,
    MemoryItem,
)
from elfie.brain.memory import MemorySystem
from elfie.brain.perception_types import PerceptionFrame, SocialPayload
from elfie.communication import CommunicationHub
from elfie.message_types import EventId, UTCDateTime


class ElfieContextSource:
    """Read bounded context and capabilities under Coordinator ownership."""

    def __init__(
        self,
        *,
        memory: MemorySystem,
        current_body: Callable[[], Optional[BodyPort]],
        communication: CommunicationHub,
        clock: Callable[[], UTCDateTime],
        history_capacity: int = 32,
        event_identity_capacity: int = 2048,
        conversations_per_channel: int = 128,
    ) -> None:
        self._memory = memory
        self._current_body = current_body
        self._communication = communication
        self._clock = clock
        self._history: Deque[ConversationMessage] = deque(maxlen=history_capacity)
        self._event_identity_capacity = event_identity_capacity
        self._conversations_per_channel = conversations_per_channel
        self._seen_conversation_events: set[EventId] = set()
        self._seen_conversation_order: Deque[EventId] = deque()
        self._recorded_owner_events: set[EventId] = set()
        self._recorded_owner_order: Deque[EventId] = deque()
        self._authorized_conversations: dict[str, Deque[str]] = {}
        self._capability_signature: Optional[Tuple[str, ...]] = None
        self._capability_revision = 0
        self._lock = Lock()

    def conversation(
        self,
        frame: PerceptionFrame,
        captured_at: UTCDateTime,
    ) -> ConversationContext:
        """Append source-preserving social events and return bounded history."""
        conversation_ids: list[str] = []
        with self._lock:
            for event in frame.events:
                payload = event.payload
                if not isinstance(payload, SocialPayload):
                    continue
                conversation_ids.append(payload.conversation_id)
                self._remember_conversation(
                    payload.channel_id,
                    payload.conversation_id,
                )
                if event.meta.event_id not in self._seen_conversation_events:
                    self._history.append(
                        ConversationMessage(
                            event_id=event.meta.event_id,
                            sender=payload.sender,
                            occurred_at=event.meta.occurred_at,
                            content=payload.content,
                        )
                    )
                    self._remember_seen_event(event.meta.event_id)
            history = tuple(self._history)
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
        frame: PerceptionFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> MemoryContext:
        """Record owner text once and retrieve one bounded compatibility excerpt."""
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
        """Capture the current Body and connected communication endpoints."""
        body = self._current_body()
        current_body = None
        signature: list[str] = []
        if body is not None:
            capabilities = body.capabilities
            current_body = BodyCapabilityDescriptor(
                body_id=body.body_id,
                capability_revision=capabilities.revision,
                sensors=tuple(sorted(capabilities.sensors)),
                actions=tuple(sorted(capabilities.actions)),
            )
            signature.extend(
                (
                    f"body:{body.body_id}",
                    f"body-revision:{capabilities.revision}",
                    f"body-connected:{body.snapshot_body(now=captured_at).connected}",
                )
            )
        with self._lock:
            authorized_conversations = {
                channel_id: tuple(sorted(conversation_ids))
                for channel_id, conversation_ids in self._authorized_conversations.items()
            }
        channels = tuple(
            ConnectedChannelDescriptor(
                channel_id=channel.channel_id,
                account_id=channel.channel_id,
                capability_revision=1,
                content_kinds=("text",),
                authorized_conversation_ids=authorized_conversations.get(
                    channel.channel_id,
                    (),
                ),
            )
            for channel in self._communication.router.list_channels()
            if channel.is_connected
        )
        for channel in channels:
            signature.append(f"channel:{channel.channel_id}")
            signature.extend(
                f"channel:{channel.channel_id}:conversation:{conversation_id}"
                for conversation_id in channel.authorized_conversation_ids
            )
        with self._lock:
            frozen_signature = tuple(signature)
            if frozen_signature != self._capability_signature:
                self._capability_revision += 1
                self._capability_signature = frozen_signature
            revision = self._capability_revision
        return EffectiveCapabilities(
            revision=revision,
            captured_at=captured_at,
            current_body=current_body,
            connected_channels=channels,
        )

    def current(self) -> EffectiveCapabilities:
        """Return a fresh capability snapshot for OutputRouter validation."""
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

    def _remember_conversation(
        self,
        channel_id: str,
        conversation_id: str,
    ) -> None:
        conversations = self._authorized_conversations.setdefault(
            channel_id,
            deque(),
        )
        if conversation_id in conversations:
            return
        conversations.append(conversation_id)
        while len(conversations) > self._conversations_per_channel:
            conversations.popleft()


__all__ = ("ElfieContextSource",)
