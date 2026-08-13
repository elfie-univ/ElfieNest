"""Lifecycle regressions for the bounded output scheduler."""

from __future__ import annotations

from threading import Event, Thread

from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionPlan,
    SpeechIntent,
)
from elfie.brain.reasoning.execution_router import OutputRouter
from elfie.brain.reasoning.execution_types import ExecutionBatch, IntentExecutionResult
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import EventId, IntentId, PlanId, TurnId
from test.elfie.brain.reasoning.test_output_router import (
    DEADLINE,
    ELFIE_ID,
    NOW,
    RecordingExecutor,
    StaticCapabilities,
    _capabilities,
    _embodied_decision,
)


class BlockingExecutor(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def execute(self, plan, intent) -> IntentExecutionResult:
        del plan
        self.calls.append(intent.intent_id)
        self.started.set()
        self.release.wait()
        return IntentExecutionResult.completed()


def _speech_plan(index: int) -> DecisionPlan:
    intent = SpeechIntent(
        type="speech",
        intent_id=IntentId(f"speech-{index}"),
        cause_event_ids=(EventId(f"cause-{index}"),),
        dependency_ids=(),
        deadline=DEADLINE,
        cancel_policy=CancelPolicy.ALWAYS,
        text=f"message {index}",
    )
    return DecisionPlan(
        plan_id=PlanId(f"plan-{index}"),
        turn_id=TurnId(f"turn-{index}"),
        frame_id=EventId(f"frame-{index}"),
        context_revision=1,
        capability_revision=7,
        created_at=NOW,
        deadline=DEADLINE,
        cause_event_ids=(EventId(f"cause-{index}"),),
        intents=(intent,),
    )


def test_stop_returns_while_the_bounded_queue_is_full() -> None:
    # Given: one executing batch and one queued batch fill all scheduler capacity.
    body = BlockingExecutor()
    router = OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities()),
        perception_sink=EventWorkspace(ELFIE_ID),
        body_executor=body,
        message_executor=RecordingExecutor(),
        internal_executor=RecordingExecutor(),
        clock=lambda: NOW,
        max_pending_batches=1,
        max_workers=1,
    )
    router.start()
    assert isinstance(
        router.submit(_embodied_decision(_speech_plan(1))), ExecutionBatch
    )
    assert body.started.wait(1)
    assert isinstance(
        router.submit(_embodied_decision(_speech_plan(2))), ExecutionBatch
    )
    returned = Event()

    def request_stop() -> None:
        router.stop()
        returned.set()

    stop_thread = Thread(target=request_stop)

    # When: lifecycle shutdown is requested while the queue is full.
    stop_thread.start()
    stopped_without_drain = returned.wait(0.2)

    # Then: stop itself is non-blocking; join remains the explicit drain boundary.
    body.release.set()
    stop_thread.join(1)
    router.join()
    assert stopped_without_drain is True


def test_decision_plan_lookup_follows_completed_retention() -> None:
    # Given: one retained completed plan and an unknown turn.
    router = OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities()),
        perception_sink=EventWorkspace(ELFIE_ID),
        body_executor=RecordingExecutor(),
        message_executor=RecordingExecutor(),
        internal_executor=RecordingExecutor(),
        clock=lambda: NOW,
        completed_retention=1,
    )
    router.start()
    first = _speech_plan(1)
    first_decision = _embodied_decision(first)
    assert isinstance(router.submit(first_decision), ExecutionBatch)
    router.wait_for_turn(first.turn_id, timeout=1)

    # When: the retained plan is looked up repeatedly.
    first_lookup = router.decision(first.turn_id)
    duplicate_lookup = router.decision(first.turn_id)

    # Then: callers receive the frozen plan and unknown turns stay absent.
    assert first_lookup is first_decision
    assert duplicate_lookup is first_decision
    assert router.decision(TurnId("turn-unknown")) is None

    # When: enough later completed turns make the first plan stale.
    second = _speech_plan(2)
    third = _speech_plan(3)
    second_decision = _embodied_decision(second)
    assert isinstance(router.submit(second_decision), ExecutionBatch)
    router.wait_for_turn(second.turn_id, timeout=1)
    assert isinstance(router.submit(_embodied_decision(third)), ExecutionBatch)

    # Then: plan visibility follows the router's existing retention boundary.
    assert router.decision(first.turn_id) is None
    assert router.decision(second.turn_id) is second_decision
    router.stop()
    router.join()
