from __future__ import annotations

from datetime import datetime, timedelta, timezone

from elfie import Elfie
from elfie.body import BodyId, CommandStatus, HeadlessBody, MotionCommand
from elfie.body.native.anatomy.biped import BipedAnatomy
from elfie.brain.emotion import EmotionSystem
from elfie.brain.workspace.contracts import PerceptionEvent, PhysicalPayload
from elfie.brain.workspace.system import EventWorkspace
from elfie.diagnostics import ElfieDiagnostics
from elfie.message_types import CommandId, ElfieId, IntentId, TurnId
from elfie.nervous_system import NervousSystem
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.nervous_system.perception_bridge_fixtures import claim_all

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


def test_nervous_system_owns_processing_components() -> None:
    nervous_system = NervousSystem()

    assert nervous_system.speech_actuator is not None
    assert nervous_system.motion_actuator is not None
    assert nervous_system.mutter_actuator is not None
    assert nervous_system.signal_filter is not None
    assert nervous_system.physical_limits is not None
    assert nervous_system.reflex is not None


def test_elfie_owns_one_canonical_nervous_system() -> None:
    elfie = Elfie(
        character_profile=create_visual_profile(
            elfie_id="elfie-nervous", display_name="神经精灵", species_id="fox", seed=1
        ),
        memory_store=SQLiteMemoryStoreAdapter.in_memory(),
    )

    assert ElfieDiagnostics(elfie).nervous_system.speech_actuator is not None
    assert ElfieDiagnostics(elfie).nervous_system.motion_actuator is not None
    assert ElfieDiagnostics(elfie).nervous_system.mutter_actuator is not None
    assert ElfieDiagnostics(elfie).nervous_system.signal_filter is not None
    assert ElfieDiagnostics(elfie).nervous_system.physical_limits is not None
    assert ElfieDiagnostics(elfie).nervous_system.reflex is not None


def test_nervous_system_filters_signals_through_existing_filter() -> None:
    nervous_system = NervousSystem()

    assert nervous_system.filter_signals({"temperature": 24.0}) is True
    assert nervous_system.filter_signals({"temperature": 24.0}) is False
    assert nervous_system.filter_signals({"temperature": 25.0}) is True


def test_nervous_system_controls_current_body_through_body_port() -> None:
    nervous_system = NervousSystem()
    body = HeadlessBody(body_id="debug")
    body.connect()
    command = MotionCommand(
        command_type="motion",
        command_id=CommandId("command-wave"),
        turn_id=TurnId("turn-wave"),
        intent_id=IntentId("intent-wave"),
        body_id=BodyId("debug"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=body.capabilities.revision,
        kind="gesture.wave",
    )

    receipts = nervous_system.execute_body_command(body, command, now=NOW)

    assert receipts[-1].status is CommandStatus.COMPLETED
    assert body.snapshot_body(now=NOW).last_command_id == command.command_id


def test_nervous_system_returns_one_terminal_action_outcome_to_workspace() -> None:
    workspace = EventWorkspace(ElfieId("action-feedback"))
    body = HeadlessBody(body_id="body-action-feedback")
    body.connect()
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ElfieId("action-feedback"),
        body_port=body,
        body_generation=1,
    )
    command = MotionCommand(
        command_type="motion",
        command_id=CommandId("command-feedback"),
        turn_id=TurnId("turn-feedback"),
        intent_id=IntentId("intent-feedback"),
        body_id=BodyId("body-action-feedback"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=body.capabilities.revision,
        kind="walk",
    )

    nervous_system.execute_body_command(body, command, now=NOW)
    frame = claim_all(workspace)

    assert len(frame.events) == 1
    event = frame.events[0]
    assert isinstance(event, PerceptionEvent)
    assert isinstance(event.payload, PhysicalPayload)
    assert event.payload.body_id == "body-action-feedback"
    assert event.payload.content == (
        "action=command-feedback; intent=intent-feedback; status=completed"
    )


def test_terminal_action_outcome_uses_injected_brain_clock() -> None:
    workspace = EventWorkspace(ElfieId("action-clock"))
    body = HeadlessBody(body_id="body-action-clock")
    body.connect()
    logical_now = NOW + timedelta(seconds=7)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ElfieId("action-clock"),
        body_port=body,
        body_generation=1,
        logical_clock=lambda: logical_now,
    )
    command = MotionCommand(
        command_type="motion",
        command_id=CommandId("command-clock"),
        turn_id=TurnId("turn-clock"),
        intent_id=IntentId("intent-clock"),
        body_id=BodyId("body-action-clock"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=body.capabilities.revision,
        kind="walk",
    )

    nervous_system.execute_body_command(body, command, now=NOW)
    frame = claim_all(workspace)

    assert frame.events[0].meta.occurred_at == logical_now
    assert frame.events[0].meta.received_at == NOW


def test_nervous_system_notifies_brain_after_direct_action_feedback() -> None:
    workspace = EventWorkspace(ElfieId("action-notification"))
    body = HeadlessBody(body_id="body-action-notification")
    body.connect()
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ElfieId("action-notification"),
        body_port=body,
        body_generation=1,
    )
    notifications: list[None] = []
    nervous_system.bind_perception_notifier(lambda: notifications.append(None))
    command = MotionCommand(
        command_type="motion",
        command_id=CommandId("command-notification"),
        turn_id=TurnId("turn-notification"),
        intent_id=IntentId("intent-notification"),
        body_id=BodyId("body-action-notification"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=body.capabilities.revision,
        kind="walk",
    )

    nervous_system.execute_body_command(body, command, now=NOW)

    assert notifications == [None]


def test_nervous_system_processes_reflex_through_existing_reflex_arc() -> None:
    nervous_system = NervousSystem()
    anatomy = BipedAnatomy()
    emotion = EmotionSystem()

    joints, event = nervous_system.process_reflex(
        anatomy,
        {"impact_force": 20.0, "impact_direction": "front"},
        emotion,
    )

    assert event["triggered"] is True
    assert event["type"] == "shock_avoidance"
    assert joints["neck_pitch"] == 0.5


def test_nervous_system_validates_and_executes_existing_actions() -> None:
    nervous_system = NervousSystem()
    anatomy = BipedAnatomy()

    assert nervous_system.validate_action("idle", anatomy)["allowed"] is True
    assert nervous_system.validate_action("jump", anatomy)["allowed"] is False
    assert nervous_system.speak("你好", anatomy.voice_profile) == "你好"
    assert nervous_system.mutter("sleeping")

    joints = nervous_system.drive(anatomy, "nod_head", elapsed_time=1.0)
    assert joints["neck_pitch"] == 0.4
    assert joints["head_yaw"] == 0.0


def test_validate_action_remains_the_physical_safety_gate() -> None:
    # Given: a biped body and an action that its morphology cannot perform.
    nervous_system = NervousSystem()
    anatomy = BipedAnatomy()

    # When: the output path asks the NervousSystem safety gate for permission.
    result = nervous_system.validate_action("wag_tail", anatomy)

    # Then: the action is rejected before any body execution can occur.
    assert result["allowed"] is False
