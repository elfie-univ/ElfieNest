"""Lifecycle regressions for the bounded output scheduler."""

from __future__ import annotations

from threading import Event, Thread

from elfie.brain.decision_types import CancelPolicy, DecisionPlan, SpeechIntent
from elfie.brain.output_router import OutputRouter
from elfie.brain.output_types import ExecutionBatch, IntentExecutionResult
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.message_types import EventId, IntentId, PlanId, TurnId
from test.elfie.brain.test_output_router import (
    DEADLINE,
    ELFIE_ID,
    NOW,
    RecordingExecutor,
    StaticCapabilities,
    _capabilities,
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
        perception_sink=PerceptualWorkspace(ELFIE_ID),
        body_executor=body,
        message_executor=RecordingExecutor(),
        internal_executor=RecordingExecutor(),
        clock=lambda: NOW,
        max_pending_batches=1,
        max_workers=1,
    )
    router.start()
    assert isinstance(router.submit(_speech_plan(1)), ExecutionBatch)
    assert body.started.wait(1)
    assert isinstance(router.submit(_speech_plan(2)), ExecutionBatch)
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
