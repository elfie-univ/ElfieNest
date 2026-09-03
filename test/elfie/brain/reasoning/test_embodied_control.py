"""Tests for the Brain-owned first-stage embodied Mock gate."""

from datetime import datetime, timedelta, timezone
from random import Random

from elfie.brain.reasoning.context_types import (
    BodyCapabilityDescriptor,
    CapabilityDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.embodied_control import EmbodiedMockController
from elfie.brain.workspace.contracts import (
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
)
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    Priority,
    TraceId,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-embodied-mock")


class StaticContext:
    def __init__(self) -> None:
        self.value = EffectiveCapabilities(
            revision=3,
            captured_at=NOW,
            current_body=BodyCapabilityDescriptor(
                body_id="body-1",
                body_generation=1,
                capability_revision=2,
                sensors=("proprioception",),
                actions=("move_to_anchor",),
            ),
            world_capabilities=("move.to",),
            capability_catalog=(
                CapabilityDescriptor(
                    capability_id="move.to",
                    category="world",
                    argument_schema={
                        "type": "object",
                        "required": ["anchor_id"],
                        "properties": {
                            "anchor_id": {
                                "type": "string",
                                "enum": ["room/chair", "room/activity"],
                            }
                        },
                    },
                ),
            ),
            connected_channels=(),
        )

    def capabilities(self, captured_at):
        return self.value.model_copy(update={"captured_at": captured_at})


class RecordingSink:
    def __init__(self) -> None:
        self.decisions = []

    def accept(self, decision) -> bool:
        self.decisions.append(decision)
        return True

    def cancel_stale(self, turn_id, reason: str) -> None:
        del turn_id, reason


def _event(event_id: str, content: str) -> PerceptionEvent:
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId(event_id),
            elfie_id=ELFIE_ID,
            source=ActorRef(actor_id=ActorId("body-1"), source_kind="body"),
            occurred_at=NOW,
            received_at=NOW,
            trace_id=TraceId(f"trace-{event_id}"),
        ),
        payload=PhysicalPayload(
            type="physical",
            body_id="body-1",
            body_generation=1,
            modality=PhysicalModality.PROPRIOCEPTION,
            content=content,
        ),
    )


def test_mock_gate_issues_semantic_move_without_model_and_consumes_terminal_feedback():
    workspace = EventWorkspace(ELFIE_ID)
    sink = RecordingSink()
    controller = EmbodiedMockController(
        elfie_id=ELFIE_ID,
        workspace=workspace,
        context_source=StaticContext(),
        plan_sink=sink,
        rng=Random(4),
        move_interval_seconds=(0.0, 0.0),
    )

    controller.on_clock(NOW)
    assert controller.drain(NOW) is True
    assert len(sink.decisions) == 1
    intent = sink.decisions[0].plan.intents[0]
    assert intent.capability_id == "move.to"
    assert intent.arguments["anchor_id"] in {"room/chair", "room/activity"}

    terminal = _event(
        "action-terminal",
        f"action=command-1; intent={intent.intent_id}; status=completed",
    )
    workspace.publish(terminal)
    assert controller.drain(NOW + timedelta(seconds=1)) is True
    assert len(sink.decisions) == 1
    assert workspace.metrics().reliable_event_count == 0


def test_mock_gate_does_not_schedule_movement_outside_local_active_window():
    workspace = EventWorkspace(ELFIE_ID)
    sink = RecordingSink()
    controller = EmbodiedMockController(
        elfie_id=ELFIE_ID,
        workspace=workspace,
        context_source=StaticContext(),
        plan_sink=sink,
        rng=Random(4),
    )
    local_tz = NOW.astimezone().tzinfo
    before_six = datetime(2026, 7, 21, 2, 0, tzinfo=local_tz).astimezone(timezone.utc)

    controller.on_clock(before_six)
    assert workspace.metrics().reliable_event_count == 0
    assert sink.decisions == []


def test_mock_gate_leaves_critical_embodied_input_for_brain():
    workspace = EventWorkspace(ELFIE_ID)
    sink = RecordingSink()
    controller = EmbodiedMockController(
        elfie_id=ELFIE_ID,
        workspace=workspace,
        context_source=StaticContext(),
        plan_sink=sink,
        rng=Random(4),
    )
    critical = _event("critical", "collision")
    workspace.publish(
        critical.model_copy(
            update={
                "meta": critical.meta.model_copy(update={"priority": Priority.CRITICAL})
            }
        )
    )

    assert controller.drain(NOW) is False
    assert workspace.metrics().reliable_event_count == 1
    assert sink.decisions == []
