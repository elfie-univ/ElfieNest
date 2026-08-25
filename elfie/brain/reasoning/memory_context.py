"""Read-only Memory retrieval and explicit candidate preparation."""

from __future__ import annotations

from typing import Literal, Tuple, cast

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.memory import EpisodicMemoryCandidate, MemorySystem
from elfie.brain.memory.contracts import (
    MemoryContext,
    MemoryItem,
)
from elfie.brain.memory.node_types import MemoryNode
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
        del emotion
        for event in frame.events:
            if isinstance(event.payload, SocialPayload):
                query_parts.append(event.payload.content)
        state = self._memory.snapshot(captured_at)
        if not query_parts:
            return MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                items=(),
                state=state,
            )
        nodes = self._memory.recall_nodes(
            query="\n".join(query_parts),
            top_k=5,
        )
        items = tuple(
            _memory_item_from_node(node) for node in nodes if node.content.strip()
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


def _memory_item_from_node(node: MemoryNode) -> MemoryItem:
    raw_source_ids = node.metadata.get("source_event_ids", ())
    if isinstance(raw_source_ids, (list, tuple)):
        source_event_ids = tuple(
            EventId(str(value).strip())
            for value in raw_source_ids
            if str(value).strip()
        )
    else:
        source_event_ids = ()
    if not source_event_ids:
        source_event_ids = (EventId(f"memory-node:{node.id}"),)

    kind = (
        node.type
        if node.type in {"episodic", "knowledge", "entity", "pattern"}
        else "episodic"
    )
    raw_source = node.metadata.get("source") or node.metadata.get("genesis_kind")
    source = str(raw_source).strip() if raw_source is not None else None
    if source == "":
        source = None
    raw_relevance = node.metadata.get("_retrieval_score", 0.5)
    try:
        relevance = min(1.0, max(0.0, float(raw_relevance)))
    except (TypeError, ValueError):
        relevance = 0.5
    return MemoryItem(
        memory_id=EventId(node.id),
        content=node.content,
        relevance=relevance,
        source_event_ids=source_event_ids,
        kind=cast(Literal["episodic", "knowledge", "entity", "pattern"], kind),
        source=source,
        certainty=cast(
            Literal["high", "medium", "low"],
            node.metadata.get("certainty", "medium")
            if node.metadata.get("certainty") in {"high", "medium", "low"}
            else "medium",
        ),
    )


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
