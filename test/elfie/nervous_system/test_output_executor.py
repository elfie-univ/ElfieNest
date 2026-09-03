"""Integration tests for physical intents crossing NervousSystem into Body."""

from threading import Event, Thread

from elfie.body import HeadlessBody
from elfie.body.capabilities import BodyCapabilities
from elfie.body.contracts import BodyCommand, CapabilityCommand, MotionCommand
from elfie.brain.reasoning.decision_types import (
    CapabilityIntent,
    MotionIntent,
    SpeechIntent,
)
from elfie.brain.reasoning.execution_types import IntentExecutionResult
from elfie.brain.workspace.contracts import ExecutionStatus
from elfie.message_types import IntentId
from elfie.nervous_system import NervousSystem
from elfie.nervous_system.output_executor import NervousSystemIntentExecutor
from test.elfie.brain.reasoning.test_output_router import NOW, _base, _plan


class RecordingBody(HeadlessBody):
    def __init__(self) -> None:
        super().__init__(
            body_id="body-1",
            capabilities=BodyCapabilities(
                sensors=frozenset({"proprioception"}),
                actions=frozenset({"move_to_anchor", "vendor.wave"}),
            ),
        )
        self.commands: list[BodyCommand] = []

    def execute(self, command: BodyCommand, *, now=None):
        self.commands.append(command)
        return super().execute(command, now=now)


def test_physical_executor_builds_correlated_typed_body_commands() -> None:
    # Given: a connected typed Body behind the NervousSystem boundary.
    body = HeadlessBody(body_id="body-1")
    body.connect()
    executor = NervousSystemIntentExecutor(
        nervous_system=NervousSystem(),
        current_body=lambda: body,
        clock=lambda: NOW,
    )
    speech = SpeechIntent(type="speech", text="hello", **_base("speech"))
    plan = _plan((speech,))

    # When: the physical intent executes.
    result = executor.execute(plan, speech)

    # Then: Body validation completed with the original turn and intent identity.
    assert result == IntentExecutionResult.completed()
    snapshot = body.snapshot_body(now=NOW)
    assert snapshot.last_status is not None
    assert snapshot.last_status.value == ExecutionStatus.COMPLETED.value


def test_capability_executor_maps_registered_world_call_to_body_command() -> None:
    body = RecordingBody()
    body.connect()
    executor = NervousSystemIntentExecutor(
        nervous_system=NervousSystem(),
        current_body=lambda: body,
        clock=lambda: NOW,
    )
    intent = CapabilityIntent(
        type="capability",
        category="world",
        capability_id="world.go_to",
        arguments={"anchor_id": "activity-01/activity"},
        **_base("go-to"),
    )

    result = executor.execute(_plan((intent,)), intent)

    assert result == IntentExecutionResult.completed()
    command = body.commands[-1]
    assert isinstance(command, MotionCommand)
    assert command.kind == "move_to_anchor"
    assert command.target == "activity-01/activity"
    assert command.intent_id == intent.intent_id


def test_capability_executor_preserves_unmapped_registered_body_call() -> None:
    body = RecordingBody()
    body.connect()
    executor = NervousSystemIntentExecutor(
        nervous_system=NervousSystem(),
        current_body=lambda: body,
        clock=lambda: NOW,
    )
    intent = CapabilityIntent(
        type="capability",
        category="body",
        capability_id="vendor.wave",
        arguments={"strength": 0.5},
        **_base("vendor-wave"),
    )

    result = executor.execute(_plan((intent,)), intent)

    assert result == IntentExecutionResult.completed()
    command = body.commands[-1]
    assert isinstance(command, CapabilityCommand)
    assert command.capability_id == "vendor.wave"
    assert command.arguments == {"strength": 0.5}


def test_physical_executor_interrupts_running_motion_with_emergency_stop() -> None:
    # Given: a motion command retained as active by the adapter.
    body = HeadlessBody(body_id="body-1")
    body.connect()
    executor = NervousSystemIntentExecutor(
        nervous_system=NervousSystem(),
        current_body=lambda: body,
        clock=lambda: NOW,
    )
    motion = MotionIntent(type="motion", motion="walk", **_base("motion"))
    plan = _plan((motion,))
    assert executor.execute(plan, motion) == IntentExecutionResult.completed()

    # When: stale cancellation requests an interrupt.
    executor.interrupt(plan.turn_id, IntentId("motion"), "emergency_stop")

    # Then: the current Body receives a correlated emergency-stop command.
    assert executor.interrupt_count == 1
    assert body.snapshot_body(now=NOW).last_status is not None


def test_completed_receipt_from_previous_body_generation_is_not_reported_successful() -> (
    None
):
    class BlockingBody(HeadlessBody):
        def __init__(self) -> None:
            super().__init__(body_id="body-old")
            self.started = Event()
            self.release = Event()

        def execute(self, command: BodyCommand, *, now=None):
            self.started.set()
            self.release.wait(1.0)
            return super().execute(command, now=now)

    old_body = BlockingBody()
    old_body.connect()
    new_body = HeadlessBody(body_id="body-new")
    new_body.connect()
    current = [old_body]
    generation = [1]
    executor = NervousSystemIntentExecutor(
        nervous_system=NervousSystem(),
        current_body=lambda: current[0],
        current_body_generation=lambda: generation[0],
        clock=lambda: NOW,
    )
    motion = MotionIntent(type="motion", motion="walk", **_base("motion"))
    plan = _plan((motion,))
    result = []

    thread = Thread(target=lambda: result.append(executor.execute(plan, motion)))
    thread.start()
    assert old_body.started.wait(1.0)
    current[0] = new_body
    generation[0] = 2
    old_body.release.set()
    thread.join(1.0)

    assert result[0].error is not None
    assert result[0].error.code == "stale_body_generation"
