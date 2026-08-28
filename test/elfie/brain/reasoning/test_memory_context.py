"""Memory-backed reasoning context must preserve durable identity and provenance."""

from __future__ import annotations

from datetime import datetime, timezone

from elfie.brain.emotion.contracts import EmotionSnapshot, EmotionValue
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.memory.node_types import MemoryNode, NodeTypes
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
from test.elfie.brain.memory.fake_store import FakeMemoryStore

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def test_memory_context_returns_real_recalled_nodes_with_provenance() -> None:
    store = FakeMemoryStore.in_memory()
    store.add_node(
        MemoryNode(
            id="genesis:knowledge:elfie-1:0",
            type=NodeTypes.KNOWLEDGE.value,
            content="我来自 Elfaria。",
            metadata={
                "genesis_kind": "knowledge_fact",
                "recall_eligible": True,
                "source": "genesis:self_model",
                "source_event_ids": ["genesis:fact:elfie-1:0"],
                "certainty": "high",
            },
        )
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

    assert len(context.items) == 1
    item = context.items[0]
    assert item.memory_id == EventId("genesis:knowledge:elfie-1:0")
    assert item.content == "我来自 Elfaria。"
    assert item.source_event_ids == (EventId("genesis:fact:elfie-1:0"),)
    assert item.kind == "knowledge"
    assert item.source == "genesis:self_model"
    assert item.certainty == "high"
    assert "memory-context:frame-1" not in str(item.memory_id)
    assert "预测灵感" not in item.content
