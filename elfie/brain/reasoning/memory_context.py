"""Read-only Memory retrieval and explicit candidate preparation."""

from __future__ import annotations

from typing import Tuple

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.memory import EpisodicMemoryCandidate, MemorySystem
from elfie.brain.memory.contracts import (
    MemoryContext,
    MemoryItem,
)
from elfie.brain.reasoning.context_types import CompletedConversationInteraction
from elfie.brain.state_lifecycle import StateCommitReceipt, StateCommitStatus
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
        """Do not persist an owner-only half interaction.

        Durable interaction candidates are prepared only after a completed
        communication receipt joins the owner's input to Elfie's actual reply.
        """
        del frame, emotion, captured_at
        return ()

    def completed_interaction_candidate(
        self,
        interaction: CompletedConversationInteraction,
    ) -> EpisodicMemoryCandidate | None:
        """Prepare one durable episode for explicit long-term owner signals."""
        if not _contains_durable_owner_signal(interaction.owner.content):
            return None
        return EpisodicMemoryCandidate(
            candidate_id=EventId(f"memory-interaction:{interaction.receipt_id}"),
            base_revision=self._memory.revision,
            content=(
                f"主人对我说: '{interaction.owner.content}'。\n"
                f"我回复主人: '{interaction.reply.content}'。\n"
                "投递结果: completed。"
            ),
            emotion="calm",
            intensity=0.0,
            stimulus=f"completed-owner-interaction:{interaction.conversation_id}",
            source_event_ids=(
                interaction.owner.event_id,
                interaction.reply.event_id,
                interaction.receipt_id,
            ),
            created_at=interaction.reply.occurred_at,
        )

    def commit_completed_interaction(
        self,
        interaction: CompletedConversationInteraction,
    ) -> StateCommitReceipt | None:
        """Commit one receipt-backed episode with one bounded stale retry."""
        candidate = self.completed_interaction_candidate(interaction)
        if candidate is None:
            return None
        receipt = self._memory.commit_episode_candidate(candidate)
        if receipt.status is StateCommitStatus.STALE:
            candidate = candidate.model_copy(
                update={"base_revision": self._memory.revision}
            )
            receipt = self._memory.commit_episode_candidate(candidate)
        return receipt

    def checkpoint(self):
        return self._memory.checkpoint()

    def validate_checkpoint(self, checkpoint) -> None:
        self._memory.validate_checkpoint(checkpoint)

    def restore(self, checkpoint) -> None:
        self._memory.restore(checkpoint)


__all__ = ("MemoryContextReader",)


_DURABLE_OWNER_SIGNALS = (
    "记住",
    "纠正",
    "不是",
    "错了",
    "我喜欢",
    "我不喜欢",
    "我更喜欢",
    "我叫",
    "叫我",
    "提醒",
    "别忘",
    "答应",
    "承诺",
    "remember",
    "correction",
    "actually",
    "i like",
    "i prefer",
    "my name is",
    "call me",
    "remind",
    "don't forget",
    "do not forget",
    "promise",
)


def _contains_durable_owner_signal(content: str) -> bool:
    normalized = content.casefold()
    return any(signal in normalized for signal in _DURABLE_OWNER_SIGNALS)
