"""Read-only Memory retrieval and explicit candidate preparation."""

from __future__ import annotations

from typing import Tuple

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.memory import EpisodicMemoryCandidate, MemorySystem
from elfie.brain.memory.contracts import (
    MemoryContext,
    MemoryItem,
)
from elfie.brain.workspace.contracts import SocialPayload, TurnFrame
from elfie.message_types import EventId, UTCDateTime


class MemoryContextReader:
    """Translate a Turn into recall results without writing the Memory owner."""

    def __init__(self, memory: MemorySystem) -> None:
        self._memory = memory

    def read(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> MemoryContext:
        query_parts: list[str] = []
        source_ids: list[EventId] = []
        dominant = emotion.dominant or "calm"
        intensity = max((value.intensity for value in emotion.values), default=0.0)
        for event in frame.events:
            if isinstance(event.payload, SocialPayload):
                query_parts.append(event.payload.content)
                source_ids.append(event.meta.event_id)
        state = self._memory.snapshot(captured_at)
        if not query_parts:
            return MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                items=(),
                state=state,
            )
        content = self._memory.recall_context(
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

    def candidates(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> Tuple[EpisodicMemoryCandidate, ...]:
        owner_events = tuple(
            event
            for event in frame.events
            if isinstance(event.payload, SocialPayload)
            and event.payload.sender.source_kind == "owner"
        )
        if not owner_events:
            return ()
        dominant = emotion.dominant or "calm"
        intensity = max((value.intensity for value in emotion.values), default=0.0)
        source_ids = tuple(event.meta.event_id for event in owner_events)
        return (
            EpisodicMemoryCandidate(
                candidate_id=EventId(f"memory-episode:{frame.frame_id}"),
                base_revision=self._memory.revision,
                content="\n".join(
                    f"主人对我说: '{event.payload.content}'。" for event in owner_events
                ),
                emotion=dominant,
                intensity=intensity * 100.0,
                stimulus=f"owner-turn:{frame.frame_id}",
                source_event_ids=source_ids,
                created_at=captured_at,
            ),
        )

    def checkpoint(self):
        return self._memory.checkpoint()

    def validate_checkpoint(self, checkpoint) -> None:
        self._memory.validate_checkpoint(checkpoint)

    def restore(self, checkpoint) -> None:
        self._memory.restore(checkpoint)


__all__ = ("MemoryContextReader",)
