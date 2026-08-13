"""Failure, dependency, and stale-cancellation tests for OutputRouter."""

from datetime import timedelta
from threading import Event

from elfie.brain.reasoning.decision_types import (
    MotionIntent,
    SpeechIntent,
)
from elfie.brain.reasoning.execution_router import OutputRouter
from elfie.brain.reasoning.execution_types import IntentExecutionResult
from elfie.brain.workspace.contracts import ExecutionStatus
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import ErrorInfo, IntentId, TurnId
from test.elfie.brain.reasoning.test_output_router import (
    ELFIE_ID,
    NOW,
    RecordingExecutor,
    StaticCapabilities,
    _base,
    _capabilities,
    _communication_decision,
    _embodied_decision,
    _message,
    _plan,
)


class FirstMessageThenBlock(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.first_sent = Event()

    def execute(self, plan, intent) -> IntentExecutionResult:
        result = super().execute(plan, intent)
        self.first_sent.set()
        return result


class InterruptibleBody(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def execute(self, plan, intent) -> IntentExecutionResult:
        del plan
        self.calls.append(intent.intent_id)
        self.started.set()
        self.release.wait()
        return IntentExecutionResult.interrupted("emergency_stop")

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        super().interrupt(turn_id, intent_id, reason)
        self.release.set()


def _router(body: RecordingExecutor, message: RecordingExecutor) -> OutputRouter:
    return OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities()),
        perception_sink=EventWorkspace(ELFIE_ID),
        body_executor=body,
        message_executor=message,
        internal_executor=RecordingExecutor(),
        clock=lambda: NOW,
    )


def test_failed_dependency_cancels_downstream_without_calling_executor() -> None:
    # Given: speech fails and motion explicitly depends on it.
    body = RecordingExecutor(
        result=IntentExecutionResult.failed(
            ErrorInfo(code="speaker_failed", message="speaker unavailable")
        )
    )
    router = _router(body, RecordingExecutor())
    router.start()
    speech = SpeechIntent(type="speech", text="hello", **_base("speech"))
    motion = MotionIntent(
        type="motion",
        motion="walk",
        **{
            **_base("motion"),
            "dependency_ids": (IntentId("speech"),),
        },
    )

    # When: the dependency graph executes.
    assert router.accept(_embodied_decision(_plan((speech, motion)))) is True
    router.wait_for_turn(TurnId("turn-router"), timeout=1)

    # Then: only speech reaches the executor and motion is cancelled by dependency.
    assert body.calls == [IntentId("speech")]
    motion_receipts = [
        receipt
        for receipt in router.receipts(TurnId("turn-router"))
        if receipt.intent_id == IntentId("motion")
    ]
    assert motion_receipts[-1].status is ExecutionStatus.CANCELLED
    assert motion_receipts[-1].error is not None
    assert motion_receipts[-1].error.code == "cancelled_dependency"
    router.stop()
    router.join()


def test_stale_cancel_keeps_sent_message_and_cancels_pending_sequence() -> None:
    # Given: message zero can finish while later messages remain pending.
    body = RecordingExecutor()
    message = FirstMessageThenBlock()
    router = _router(body, message)
    router.start()
    plan = _plan(tuple(_message(index) for index in range(3)))
    assert router.accept(_communication_decision(plan)) is True
    assert message.first_sent.wait(1)

    # When: an emergency marks the turn stale before the next sequence item starts.
    router.cancel_for_stale_turn(plan.turn_id, "emergency_stop")
    router.wait_for_turn(plan.turn_id, timeout=1)

    # Then: sent truth is retained and pending messages cancel.
    assert message.calls == [IntentId("message-0")]
    terminal = {
        receipt.intent_id: receipt.status
        for receipt in router.receipts(plan.turn_id)
        if receipt.status
        in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.INTERRUPTED,
            ExecutionStatus.CANCELLED,
        }
    }
    assert terminal[IntentId("message-0")] is ExecutionStatus.COMPLETED
    assert terminal[IntentId("message-1")] is ExecutionStatus.CANCELLED
    assert terminal[IntentId("message-2")] is ExecutionStatus.CANCELLED
    router.stop()
    router.join()


def test_stale_cancel_wakes_message_waiting_for_send_after() -> None:
    # Given: a future message is waiting in an executor worker, not the Brain thread.
    message = RecordingExecutor()
    router = _router(RecordingExecutor(), message)
    router.start()
    delayed = _message(0).model_copy(update={"send_after": NOW + timedelta(seconds=5)})
    plan = _plan((delayed,))
    assert router.accept(_communication_decision(plan)) is True

    # When: stale cancellation arrives before the scheduled send time.
    router.cancel_for_stale_turn(plan.turn_id, "emergency_stop")
    router.wait_for_turn(plan.turn_id, timeout=1)

    # Then: the wait wakes immediately and no platform call occurs.
    assert message.calls == []
    assert router.receipts(plan.turn_id)[-1].status is ExecutionStatus.CANCELLED
    router.stop()
    router.join()
