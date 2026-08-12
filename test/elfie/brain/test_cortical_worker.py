"""Lifecycle and serialization tests for the per-Elfie cortical worker."""

import json
from datetime import datetime, timedelta, timezone
from threading import Event, Lock

import pytest

from elfie.brain.cortical_worker import (
    CorticalTask,
    CorticalWorker,
    WorkerCapacityError,
    WorkerNotRunningError,
    WorkerQueueFullError,
)
from elfie.brain.decision_decoder import DecisionDecodeSeed, DecisionPlanDecoder
from elfie.brain.perception_types import InternalScope, ResponseScope, SourceDomain
from elfie.brain.runtime_port import (
    JsonSchemaDocument,
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.message_types import EventId, TurnId

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
DEADLINE = NOW + timedelta(seconds=45)


def _plan_json(turn_id: str) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "plan_id": f"plan-{turn_id}",
            "turn_id": turn_id,
            "frame_id": "frame-1",
            "context_revision": 1,
            "capability_revision": 1,
            "created_at": NOW.isoformat(),
            "deadline": DEADLINE.isoformat(),
            "cause_event_ids": ["event-1"],
            "intents": [
                {
                    "type": "speech",
                    "intent_id": f"speech-{turn_id}",
                    "cause_event_ids": ["event-1"],
                    "dependency_ids": [],
                    "deadline": DEADLINE.isoformat(),
                    "cancel_policy": "if_not_started",
                    "text": "hello",
                }
            ],
        }
    )


def _task(turn_id: str) -> CorticalTask:
    return CorticalTask(
        request=ModelGenerationRequest(
            turn_id=TurnId(turn_id),
            frame_id=EventId("frame-1"),
            context_revision=1,
            capability_revision=1,
            created_at=NOW,
            deadline=DEADLINE,
            cause_event_ids=(EventId("event-1"),),
            source_domain=SourceDomain.INTERNAL,
            interaction_scope=InternalScope(cause_id="event-1"),
            response_scope=ResponseScope(external_domain=None),
            system_prompt="Return a safe DecisionPlan.",
            user_prompt="event data",
            response_schema=JsonSchemaDocument(
                name="DecisionPlan",
                schema={"type": "object"},
            ),
        ),
        seed=DecisionDecodeSeed(
            turn_id=TurnId(turn_id),
            frame_id=EventId("frame-1"),
            context_revision=1,
            capability_revision=1,
            created_at=NOW,
            deadline=DEADLINE,
            cause_event_ids=(EventId("event-1"),),
        ),
    )


def test_schema_document_accepts_its_canonical_field_name() -> None:
    # Given / When: Brain constructs the provider-neutral schema contract.
    schema = JsonSchemaDocument(name="DecisionPlan", document={"type": "object"})

    # Then: orchestration can read the same canonical field without an alias error.
    assert schema.document == {"type": "object"}


class BlockingRuntime:
    def __init__(self) -> None:
        self.release = Event()
        self.first_started = Event()
        self.second_started = Event()
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="fake",
            model_key="fake/schema",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(str(request.turn_id))
            call_count = len(self.calls)
        self.first_started.set()
        if call_count == 2:
            self.second_started.set()
        self.release.wait()
        with self.lock:
            self.active -= 1
        return ModelGenerationResult(
            text=_plan_json(str(request.turn_id)),
            selected_mode=StructuredOutputMode.JSON_SCHEMA,
            provider="fake",
            model_key="fake/schema",
        )


def test_worker_serializes_submissions_and_has_explicit_lifecycle() -> None:
    # Given: one started worker and a blocking first generation.
    runtime = BlockingRuntime()
    worker = CorticalWorker(model_port=runtime, decoder=DecisionPlanDecoder())
    worker.start()
    worker.start()

    # When: two turns are submitted before the first completes.
    first = worker.submit(_task("turn-1"))
    runtime.first_started.wait()
    second = worker.submit(_task("turn-2"))

    # Then: only one model call is active, and both complete in order.
    assert runtime.calls == ["turn-1"]
    runtime.release.set()
    assert first.result(timeout=1).decode.plan.turn_id == TurnId("turn-1")
    assert second.result(timeout=1).decode.plan.turn_id == TurnId("turn-2")
    assert runtime.max_active == 1
    worker.stop()
    worker.stop()
    worker.join()
    worker.join()
    with pytest.raises(WorkerNotRunningError):
        worker.submit(_task("turn-3"))


def test_worker_bounds_isolated_hung_provider_calls() -> None:
    # Given: two provider calls have each occupied an isolation slot.
    runtime = BlockingRuntime()
    worker = CorticalWorker(model_port=runtime, decoder=DecisionPlanDecoder())
    worker.start()
    first = worker.submit(_task("turn-1"))
    assert runtime.first_started.wait(1)
    worker.abandon(first)
    second = worker.submit(_task("turn-2"))
    assert runtime.second_started.wait(1)
    worker.abandon(second)

    try:
        # When / Then: a third call is rejected instead of creating another thread.
        with pytest.raises(WorkerCapacityError) as captured:
            worker.submit(_task("turn-3"))
        assert captured.value.active_calls == 2
        assert captured.value.capacity == 2
    finally:
        worker.stop()
        worker.join()
        runtime.release.set()

    assert first.result(timeout=1).decode.plan.turn_id == TurnId("turn-1")
    assert second.result(timeout=1).decode.plan.turn_id == TurnId("turn-2")


def test_worker_rejects_submissions_when_queue_is_full() -> None:
    # Given: one active generation and one queued task fill the queue.
    runtime = BlockingRuntime()
    worker = CorticalWorker(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        max_queued_tasks=1,
    )
    worker.start()
    first = worker.submit(_task("turn-1"))
    assert runtime.first_started.wait(1)
    queued = worker.submit(_task("turn-2"))

    try:
        # When / Then: the next queued task is rejected without growing memory.
        with pytest.raises(WorkerQueueFullError) as captured:
            worker.submit(_task("turn-3"))
        assert captured.value.queued_tasks == 1
        assert captured.value.capacity == 1
    finally:
        runtime.release.set()
        first.result(timeout=1)
        queued.result(timeout=1)
        worker.stop()
        worker.join()


class RepairRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> ModelGenerationCapabilities:
        return BlockingRuntime().capabilities()

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.calls += 1
        text = "{broken" if self.calls == 1 else _plan_json(str(request.turn_id))
        return ModelGenerationResult(
            text=text,
            selected_mode=StructuredOutputMode.JSON_SCHEMA,
            provider="fake",
            model_key="fake/schema",
        )


def test_worker_runs_at_most_one_repair_inside_worker_thread() -> None:
    # Given: a runtime whose first result is malformed and second is valid.
    runtime = RepairRuntime()
    worker = CorticalWorker(model_port=runtime, decoder=DecisionPlanDecoder())
    worker.start()

    # When: one cortical task runs.
    result = worker.submit(_task("turn-1")).result(timeout=1)

    # Then: exactly one repair occurs without blocking the coordinator thread.
    assert runtime.calls == 2
    assert result.decode.report.repair_count == 1
    assert result.decode.plan.turn_id == TurnId("turn-1")
    worker.stop()
    worker.join()
