"""Read-only Memory retrieval and explicit candidate preparation."""

from __future__ import annotations

from typing import Literal, Tuple, cast

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.memory import EpisodicMemoryCandidate, MemorySystem
from elfie.brain.memory.contracts import (
    MemoryContext,
    MemoryItem,
)
from elfie.brain.memory.memory_records import RecallBundle, RecallRequest
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
        query = "\n".join(query_parts)
        try:
            bundle = self._memory.recall(
                RecallRequest(
                    text=query,
                    mode="basic_local",
                    seed_limit=8,
                    node_limit=32,
                    assertion_limit=48,
                    episode_limit=8,
                    evidence_limit=16,
                    character_limit=6000,
                )
            )
        except (TypeError, AttributeError):
            # Keep semantic Fakes and older injected stores usable while the
            # target adapter is being adopted.  Production SQLite follows the
            # typed RecallBundle path above.
            nodes = self._memory.recall_nodes(query=query, top_k=5)
            items = tuple(
                _memory_item_from_node(node) for node in nodes if node.content.strip()
            )
        else:
            items = _memory_items_from_bundle(bundle)
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

    kind = _memory_item_kind(node.type)
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
        kind=kind,
        source=source,
        certainty=cast(
            Literal["high", "medium", "low"],
            node.metadata.get("certainty", "medium")
            if node.metadata.get("certainty") in {"high", "medium", "low"}
            else "medium",
        ),
    )


def _memory_items_from_bundle(bundle: RecallBundle) -> Tuple[MemoryItem, ...]:
    """Project structured recall into independent, provenance-bearing items."""
    evidence_sources = {
        evidence.evidence_id: EventId(str(evidence.source_id))
        for evidence in bundle.evidence
        if str(evidence.source_id).strip()
    }
    assertion_sources: dict[str, tuple[EventId, ...]] = {}
    for assertion in bundle.assertions:
        assertion_source_ids = tuple(
            evidence_sources[evidence_id]
            for evidence_id in assertion.evidence_ids
            if evidence_id in evidence_sources
        )
        assertion_sources[assertion.assertion_id] = tuple(
            dict.fromkeys(assertion_source_ids)
        )

    items: list[MemoryItem] = []
    seen_ids: set[str] = set()
    for node in bundle.focus_nodes:
        if not node.label.strip() or node.node_id in seen_ids:
            continue
        node_sources: list[EventId] = []
        for assertion in bundle.assertions:
            if node.node_id in {assertion.subject_id, assertion.object_node_id}:
                node_sources.extend(assertion_sources.get(assertion.assertion_id, ()))
        # A graph node without a sourced assertion is still useful as a
        # semantic anchor, but it must not be presented as if the node ID were
        # an originating event.  Provenance is empty until a real Episode or
        # seed evidence link is available.
        source_ids = tuple(dict.fromkeys(node_sources))
        kind = _memory_item_kind(node.node_type)
        content = node.label
        if node.description and node.description != node.label:
            content = f"{node.label}：{node.description}"
        items.append(
            MemoryItem(
                memory_id=EventId(node.node_id),
                content=content,
                relevance=max(0.0, min(1.0, node.relevance)),
                source_event_ids=source_ids,
                kind=kind,
                source="memory_recall",
                certainty="medium",
            )
        )
        seen_ids.add(node.node_id)
        if len(items) >= 8:
            return tuple(items)
    for episode in bundle.episodes:
        if episode.episode_id in seen_ids or not episode.excerpt.strip():
            continue
        items.append(
            MemoryItem(
                memory_id=EventId(episode.episode_id),
                content=episode.excerpt,
                relevance=max(0.0, min(1.0, episode.relevance)),
                source_event_ids=(EventId(episode.episode_id),),
                kind="episodic",
                source="episode",
                certainty="medium",
            )
        )
        seen_ids.add(episode.episode_id)
        if len(items) >= 8:
            break
    return tuple(items)


def _memory_item_kind(
    node_type: str,
) -> Literal["episodic", "knowledge", "entity", "pattern"]:
    """Map heterogeneous graph node types to the stable Brain item taxonomy."""
    if node_type in {"episodic", "event"}:
        return "episodic"
    if node_type == "pattern":
        return "pattern"
    if node_type in {
        "entity",
        "elfie",
        "person",
        "animal",
        "place",
        "object",
        "group",
    }:
        return "entity"
    return "knowledge"


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
