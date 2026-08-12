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
    OrientationSnapshot,
    ProfileAnchorSnapshot,
    SelfhoodSnapshot,
)
from elfie.brain.memory import MemorySystem
from elfie.brain.orientation import OrientationSystem
from elfie.brain.perception_types import SocialPayload, TurnFrame
from elfie.brain.selfhood import SelfhoodSystem
from elfie.message_types import EventId, TurnId, UTCDateTime

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
        orientation: OrientationSystem | None = None,
        selfhood: SelfhoodSystem | None = None,
        profile_anchors: ProfileAnchorSnapshot | None = None,
        history_capacity: int = 32,
        event_identity_capacity: int = 2048,
        conversations_per_channel: int = 128,
    ) -> None:
        self._memory = memory
        self._capability_reader = capability_reader
        self._clock = clock
        self._orientation = orientation or OrientationSystem(initial_at=clock())
        self._selfhood = selfhood or SelfhoodSystem(initial_at=clock())
        self._profile_anchors = (
            profile_anchors
            or ProfileAnchorSnapshot.unknown().model_copy(
                update={"captured_at": clock()}
            )
        )
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
        history: Tuple[ConversationMessage, ...] = ()
        with self._lock:
            for event in frame.events:
                payload = event.payload
                if not isinstance(payload, SocialPayload):
                    continue
                conversation_ids.append(payload.conversation_id)
                active_key = (payload.channel_id, payload.conversation_id)
                self._remember_conversation(payload.channel_id, payload.conversation_id)
                if event.meta.event_id not in self._seen_conversation_events:
                    conversation_history = self._histories.setdefault(
                        active_key,
                        deque(maxlen=self._history_capacity),
                    )
                    conversation_history.append(
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
                    source_event_ids=(event.meta.event_id,),
                )
                self._remember_recorded_owner_event(event.meta.event_id)
        state = self._memory.snapshot(captured_at)
        if not query_parts:
            return MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                items=(),
                state=state,
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
            state=state,
        )

    def memory_checkpoint(self):
        """Expose the Memory owner's persistence-neutral continuity checkpoint."""
        return self._memory.checkpoint()

    def restore_memory_checkpoint(self, checkpoint) -> None:
        """Restore Memory continuity after the durable store is verified."""
        self._memory.restore(checkpoint)

    def validate_memory_checkpoint(self, checkpoint) -> None:
        """Validate Memory continuity without mutating the owner."""
        self._memory.validate_checkpoint(checkpoint)

    def capabilities(self, captured_at: UTCDateTime) -> EffectiveCapabilities:
        """Read a sibling-free capability projection through the injected reader."""
        with self._lock:
            authorized = {
                channel_id: tuple(conversations)
                for channel_id, conversations in self._authorized_conversations.items()
            }
        return self._capability_reader(captured_at, authorized)

    def orientation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
        turn_id: TurnId,
        capabilities: EffectiveCapabilities,
    ) -> OrientationSnapshot:
        """Explicitly observe the admitted frame before context assembly."""
        snapshot, _receipt = self._orientation.observe(
            frame=frame,
            capabilities=capabilities,
            turn_id=turn_id,
            captured_at=captured_at,
        )
        return snapshot

    def orientation_snapshot(self) -> OrientationSnapshot:
        """Return the latest committed orientation without mutating it."""
        return self._orientation.snapshot()

    def selfhood(self, captured_at: UTCDateTime) -> SelfhoodSnapshot:
        """Read the committed Selfhood snapshot without accepting Turn text."""
        snapshot = self._selfhood.snapshot()
        return snapshot.model_copy(update={"captured_at": captured_at})

    def selfhood_snapshot(self) -> SelfhoodSnapshot:
        """Return the latest committed Selfhood without changing its revision."""
        return self._selfhood.snapshot()

    def profile_anchors(self, captured_at: UTCDateTime) -> ProfileAnchorSnapshot:
        """Project immutable Profile anchors at the current context cutoff."""
        return self._profile_anchors.model_copy(update={"captured_at": captured_at})

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
