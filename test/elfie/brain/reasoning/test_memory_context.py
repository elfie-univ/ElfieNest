"""Memory-backed reasoning context must preserve durable identity and provenance."""

from __future__ import annotations

from datetime import datetime, timezone

from elfie.brain.emotion.contracts import EmotionSnapshot, EmotionValue
from elfie.brain.memory.memory_records import AssertionInput, EvidenceInput, NodeInput
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.reasoning.memory_context import MemoryContextReader
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

    context = MemoryContextReader(memory).read(
        frame,
        EmotionSnapshot(
            revision=1,
            captured_at=NOW,
            values=(EmotionValue(name="curiosity", intensity=0.5),),
            dominant="curiosity",
        ),
        NOW,
    )

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
