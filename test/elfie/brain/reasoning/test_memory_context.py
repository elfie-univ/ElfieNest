"""Memory-backed reasoning context must preserve durable identity and provenance."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    NodeInput,
)
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.reasoning.memory_context import ReasoningMemoryBridge
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    PerceptionEvent,
    ResponseScope,
    SocialPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import ActorRef, ElfieId, EventId, MessageMeta, TraceId
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _owner_frame(text: str, *, index: int = 1) -> TurnFrame:
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    return TurnFrame(
        frame_id=EventId(f"frame-{index}"),
        elfie_id=ElfieId("elfie-1"),
        revision=index,
        captured_at=NOW,
        cutoff_seq=index,
        trigger_reason=TriggerReason.CONVERSATION_QUIET,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="godot-owner", conversation_id="owner:1"
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="godot-owner",
            conversation_id="owner:1",
        ),
        events=(
            PerceptionEvent(
                meta=MessageMeta(
                    event_id=EventId(f"owner-event-{index}"),
                    elfie_id=ElfieId("elfie-1"),
                    source=owner,
                    occurred_at=NOW,
                    received_at=NOW,
                    trace_id=TraceId(f"trace-{index}"),
                ),
                payload=SocialPayload(
                    type="social",
                    channel_id="godot-owner",
                    conversation_id="owner:1",
                    sender=owner,
                    content=text,
                ),
            ),
        ),
    )


def test_memory_context_returns_real_recalled_nodes_with_provenance() -> None:
    store = SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-1")
    store.upsert_node_record(
        NodeInput(
            node_id="genesis:knowledge:elfie-1:0",
            node_type="knowledge",
            canonical_label="我来自 Elfaria。",
            description="我来自 Elfaria。",
            properties={
                "genesis_kind": "knowledge_fact",
                "recall_eligible": True,
                "source": "genesis:self_model",
                "source_event_ids": ["genesis:fact:elfie-1:0"],
                "certainty": "high",
            },
            confidence=1.0,
            importance=1.0,
        )
    )
    store.record_sourced_assertion(
        AssertionInput(
            "genesis:knowledge:elfie-1:0",
            "references",
            object_literal="genesis:self-model",
            evidence_ids=("genesis:evidence:elfie-1:0",),
            confidence=1.0,
            importance=1.0,
        ),
        EvidenceInput(
            "genesis:evidence:elfie-1:0",
            "seed",
            "genesis:fact:elfie-1:0",
            excerpt="我来自 Elfaria。",
        ),
    )
    memory = MemorySystem(store, elfie_id="elfie-1", initial_at=NOW)
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    frame = TurnFrame(
        frame_id=EventId("frame-1"),
        elfie_id=ElfieId("elfie-1"),
        revision=1,
        captured_at=NOW,
        cutoff_seq=1,
        trigger_reason=TriggerReason.CONVERSATION_QUIET,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="godot-owner", conversation_id="owner:1"
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="godot-owner",
            conversation_id="owner:1",
        ),
        events=(
            PerceptionEvent(
                meta=MessageMeta(
                    event_id=EventId("owner-event-1"),
                    elfie_id=ElfieId("elfie-1"),
                    source=owner,
                    occurred_at=NOW,
                    received_at=NOW,
                    trace_id=TraceId("trace-1"),
                ),
                payload=SocialPayload(
                    type="social",
                    channel_id="godot-owner",
                    conversation_id="owner:1",
                    sender=owner,
                    content="你来自哪里？",
                ),
            ),
        ),
    )

    turn = ReasoningMemoryBridge(memory).open_turn(
        frame,
        EmotionSnapshot.inactive(captured_at=NOW, revision=1),
        NOW,
    )

    context = turn.context
    bundle = context.recall
    assert context.recall_revision == memory.revision
    assert bundle.recall_revision == memory.revision
    assert len(bundle.focus_nodes) == 1
    node = bundle.focus_nodes[0]
    assert node.node_id == "genesis:knowledge:elfie-1:0"
    assert node.label == "我来自 Elfaria。"
    assert node.importance == 1.0
    assert len(bundle.assertions) == 1
    assertion = bundle.assertions[0]
    assert assertion.evidence_ids == ("genesis:evidence:elfie-1:0",)
    assert bundle.evidence[0].source_id == "genesis:fact:elfie-1:0"
    assert "memory-context:frame-1" not in str(node.node_id)
    assert "预测灵感" not in node.label


def test_relationship_importance_uses_entity_metadata_not_retrieval_score() -> None:
    store = SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-1")
    store.upsert_node_record(
        NodeInput(
            node_id="person:owner-1",
            node_type="entity",
            canonical_label="主人",
            properties={
                "person_id": "owner-1",
                "is_owner": True,
                "importance_score": 0.85,
                "retrieval_relevance": 0.02,
            },
            importance=0.85,
        )
    )
    memory = MemorySystem(store, elfie_id="elfie-1", initial_at=NOW)

    relationship = memory.relationship_importance("owner-1", owner=True)

    assert relationship is not None
    assert relationship.importance == 0.85
    assert relationship.revision == memory.revision


def test_relationship_importance_rejects_an_ambiguous_owner_fallback() -> None:
    store = SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-1")
    for person_id in ("owner-a", "owner-b"):
        store.upsert_node_record(
            NodeInput(
                node_id=f"person:{person_id}",
                node_type="entity",
                canonical_label=person_id,
                properties={
                    "person_id": person_id,
                    "is_owner": True,
                    "importance_score": 0.8,
                },
                importance=0.8,
            )
        )
    memory = MemorySystem(store, elfie_id="elfie-1", initial_at=NOW)

    assert memory.relationship_importance("unknown-owner", owner=True) is None


def test_smalltalk_skips_baseline_recall_without_hiding_the_status() -> None:
    memory = MemorySystem(
        SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-1"),
        elfie_id="elfie-1",
        initial_at=NOW,
    )

    with patch.object(memory, "recall", wraps=memory.recall) as recall:
        turn = ReasoningMemoryBridge(memory).open_turn(
            _owner_frame("你好呀"),
            EmotionSnapshot.inactive(captured_at=NOW, revision=1),
            NOW,
        )

    assert turn.session.baseline_result.status == "skipped"
    assert turn.session.baseline_result.reason == "baseline_recall_not_relevant"
    assert turn.context.recall_revision == memory.revision
    recall.assert_not_called()


def test_on_demand_recall_is_deduplicated_and_rejects_a_new_revision() -> None:
    memory = MemorySystem(
        SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-1"),
        elfie_id="elfie-1",
        initial_at=NOW,
    )
    bridge = ReasoningMemoryBridge(memory)
    inactive = EmotionSnapshot.inactive(captured_at=NOW, revision=1)
    turn = bridge.open_turn(_owner_frame("你好呀"), inactive, NOW)

    first = turn.session.recall("主人以前喜欢什么？")
    duplicate = turn.session.recall("  主人以前喜欢什么？  ")

    assert first.status == "recalled"
    assert first.bundle is not None
    assert first.bundle.recall_revision == turn.session.pinned_revision
    assert duplicate.status == "duplicate"
    assert duplicate.bundle == first.bundle

    stale_turn = bridge.open_turn(_owner_frame("继续聊", index=2), inactive, NOW)
    memory.record_closed_episode(
        ClosedEpisode(
            episode_id="episode-after-pin",
            idempotency_key="episode-after-pin",
            occurred_from=NOW.isoformat(),
            content_text="主人纠正了旧偏好。",
            source_event_ids=("owner-event-correction",),
        )
    )

    stale = stale_turn.session.recall("主人纠正后的偏好是什么？")
    assert stale.status == "stale"
    assert stale.bundle is None
    assert stale.reason == "memory_revision_changed_before_recall"


def test_memory_failure_is_an_explicit_unavailable_recall_result() -> None:
    class UnavailableMemory:
        revision = 0

        def snapshot(self, captured_at):
            del captured_at
            raise OSError("memory offline")

        def recall(self, request):
            del request
            raise OSError("memory offline")

    turn = ReasoningMemoryBridge(UnavailableMemory()).open_turn(  # type: ignore[arg-type]
        _owner_frame("你还记得我喜欢什么吗？"),
        EmotionSnapshot.inactive(captured_at=NOW, revision=1),
        NOW,
    )

    assert turn.session.baseline_result.status == "unavailable"
    assert turn.session.baseline_result.reason == "memory_unavailable:OSError"
    assert turn.context.recall.focus_nodes == ()


def test_restart_recall_keeps_the_corrected_fact_and_both_sources(
    tmp_path: Path,
) -> None:
    memory_path = tmp_path / "memory" / "knowledge.sqlite"
    memory_path.parent.mkdir(parents=True)
    store = SQLiteMemoryStoreAdapter(memory_path, elfie_id="elfie-1")
    store.record_episode(
        ClosedEpisode(
            episode_id="episode-old-name",
            idempotency_key="episode-old-name",
            occurred_from="2026-01-01T00:00:00+00:00",
            content_text="主人以前叫小林。",
            source_event_ids=("owner-old-name",),
        )
    )
    store.record_episode(
        ClosedEpisode(
            episode_id="episode-new-name",
            idempotency_key="episode-new-name",
            occurred_from="2026-01-02T00:00:00+00:00",
            content_text="主人纠正：不叫小林，叫小周。",
            source_event_ids=("owner-new-name",),
        )
    )
    store.apply_consolidation(
        ConsolidationProjection(
            episode_id="episode-old-name",
            nodes=(NodeInput("owner", "person", "主人"),),
            evidence=(
                EvidenceInput(
                    "evidence-old-name",
                    "episode",
                    "episode-old-name",
                    excerpt="主人以前叫小林。",
                ),
            ),
            assertions=(
                AssertionInput(
                    "owner",
                    "preferred_name",
                    object_literal="小林",
                    evidence_ids=("evidence-old-name",),
                    assertion_id="claim-old-name",
                ),
            ),
        )
    )
    store.apply_consolidation(
        ConsolidationProjection(
            episode_id="episode-new-name",
            evidence=(
                EvidenceInput(
                    "evidence-new-name",
                    "episode",
                    "episode-new-name",
                    excerpt="主人纠正：不叫小林，叫小周。",
                ),
            ),
            assertions=(
                AssertionInput(
                    "owner",
                    "preferred_name",
                    object_literal="小周",
                    context="correction",
                    evidence_ids=("evidence-new-name",),
                    assertion_id="claim-new-name",
                ),
            ),
        )
    )
    store.close()

    reopened = SQLiteMemoryStoreAdapter(memory_path, elfie_id="elfie-1")
    try:
        memory = MemorySystem(reopened, elfie_id="elfie-1", initial_at=NOW)
        turn = ReasoningMemoryBridge(memory).open_turn(
            _owner_frame("你还记得主人之前叫什么吗？"),
            EmotionSnapshot.inactive(captured_at=NOW, revision=1),
            NOW,
        )
        bundle = turn.context.recall

        assert turn.session.baseline_result.status == "recalled"
        claims = {item.assertion_id: item for item in bundle.assertions}
        assert claims["claim-new-name"].status == "active"
        assert claims["claim-new-name"].object_literal == "小周"
        assert claims["claim-old-name"].status == "superseded"
        assert {item.source_id for item in bundle.evidence} == {
            "episode-old-name",
            "episode-new-name",
        }
    finally:
        reopened.close()
