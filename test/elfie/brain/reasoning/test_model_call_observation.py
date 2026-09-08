"""model_call observations emitted at the Brain agent-loop model boundary."""

from __future__ import annotations

from threading import Lock
from typing import List, Tuple

import pytest

from elfie.brain.observation import (
    BrainObservation,
    ObservationStatus,
)
from elfie.brain.reasoning.agent_loop_observations import ModelCallObservation
from elfie.brain.reasoning.decision_decoder import DecisionPlanDecoder
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.brain.reasoning.run import ReasoningRun, ReasoningStatus
from test.elfie.brain.reasoning.test_reasoning import _plan_json, _task

AGENT_LOOP_MODEL_CALLS = ("reasoning.agent_loop", "model_call")


class _CollectorSink:
    """Thread-safe in-memory sink recording every emitted observation."""

    def __init__(self) -> None:
        self._events: List[BrainObservation] = []
        self._lock = Lock()

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        with self._lock:
            return tuple(self._events)

    def model_calls(self) -> Tuple[BrainObservation, ...]:
        return tuple(
            event
            for event in self.snapshot()
            if (event.boundary, event.kind) == AGENT_LOOP_MODEL_CALLS
        )


class _FakeModelRuntime:
    """Deterministic schema-capable port returning one scripted text per call."""

    provider = "fake"
    model_key = "fake/schema"

    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: List[ModelGenerationRequest] = []

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider=self.provider,
            model_key=self.model_key,
            supports_json_schema=True,
            supports_tool_calling=True,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        return ModelGenerationResult(
            text=self._texts.pop(0),
            selected_mode=StructuredOutputMode.JSON_TEXT,
            provider=self.provider,
            model_key=self.model_key,
            prompt_tokens=21,
            completion_tokens=7,
            latency_ms=1.5,
        )


class _FailingModelRuntime(_FakeModelRuntime):
    """Raise a fixed provider exception on the first generate call."""

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        raise RuntimeError("provider secret exploded")


def test_completed_model_call_emits_agent_loop_observation() -> None:
    sink = _CollectorSink()
    plan_json = _plan_json("turn-1")
    runtime = _FakeModelRuntime(plan_json)

    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        observation_sink=sink,
    ).run(_task())

    assert result.status is ReasoningStatus.COMPLETED
    calls = sink.model_calls()
    assert len(calls) == 1
    event = calls[0]
    assert event.boundary == "reasoning.agent_loop"
    assert event.kind == "model_call"
    assert event.sequence == 1
    assert event.status is ObservationStatus.completed
    assert event.error is None
    assert event.turn_id == "turn-1"
    assert event.frame_id == "frame-1"
    assert event.cause_event_ids == ("event-1",)
    assert event.duration_ms is not None and event.duration_ms >= 0.0

    payload = event.payload
    assert isinstance(payload, ModelCallObservation)
    assert payload.iteration_index == 1
    assert payload.provider == "fake"
    assert payload.model_key == "fake/schema"
    assert payload.duration_ms == event.duration_ms
    assert payload.response_text == plan_json
    assert payload.selected_mode == "json_text"
    assert payload.system_prompt == "Return a safe DecisionPlan."
    assert payload.user_prompt == "event data"
    assert payload.reasoning_mode == "fast"
    assert payload.response_mode == "decision_plan"
    assert payload.response_schema_name == "DecisionPlan"
    assert payload.temperature == 0.2
    assert payload.max_tokens == 512
    assert payload.context_revision == 1
    assert payload.capability_revision == 1
    assert payload.prompt_tokens == 21
    assert payload.completion_tokens == 7
    assert payload.provider_latency_ms == 1.5
    assert payload.allowed_tools == ()
    assert payload.tool_definition_count == 0
    assert payload.skill_count == 0
    assert payload.deadline is not None
    assert payload.created_at is not None


def test_repair_generation_emits_its_own_model_call_observation() -> None:
    sink = _CollectorSink()
    runtime = _FakeModelRuntime("not a decision plan json", _plan_json("turn-1"))

    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        observation_sink=sink,
    ).run(_task())

    assert result.status is ReasoningStatus.COMPLETED
    assert result.model_calls == 2
    calls = sink.model_calls()
    assert len(calls) == 2
    assert [event.payload.iteration_index for event in calls] == [1, 2]
    assert [event.sequence for event in calls] == [1, 2]
    assert all(event.status is ObservationStatus.completed for event in calls)
    assert calls[1].payload.user_prompt.startswith("Repair the following")
    assert calls[1].payload.response_text == _plan_json("turn-1")


def test_failed_model_call_emits_failed_observation_and_settles_as_before() -> None:
    sink = _CollectorSink()
    runtime = _FailingModelRuntime()

    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        observation_sink=sink,
    ).run(_task())

    # The provider exception still propagates to the unchanged Run failure
    # path: same status, same reason, and the call counter never advanced.
    assert result.status is ReasoningStatus.FAILED
    assert result.failure_reason == "model_unavailable:RuntimeError"
    assert result.model_calls == 0
    assert not any(step.kind.value == "model" for step in result.steps)

    calls = sink.model_calls()
    assert len(calls) == 1
    event = calls[0]
    assert event.status is ObservationStatus.failed
    assert event.error is not None
    assert event.error.type == "RuntimeError"
    assert event.error.message == "model_generate_failed:RuntimeError"
    # The untrusted provider exception text never enters the observation.
    assert "secret" not in event.error.message
    assert "exploded" not in event.error.message

    payload = event.payload
    assert isinstance(payload, ModelCallObservation)
    assert payload.iteration_index == 1
    assert payload.response_text is None
    assert payload.selected_mode is None
    assert payload.provider == "fake"
    assert payload.model_key == "fake/schema"
    assert payload.duration_ms is not None and payload.duration_ms >= 0.0


def test_no_model_call_observation_is_constructed_without_a_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError("model_call observation constructed without a sink")

    monkeypatch.setattr(ModelCallObservation, "__init__", _forbid_construction)
    monkeypatch.setattr(BrainObservation, "__init__", _forbid_construction)

    runtime = _FakeModelRuntime(_plan_json("turn-1"))
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
    ).run(_task())

    assert result.status is ReasoningStatus.COMPLETED
    assert len(runtime.requests) == 1
