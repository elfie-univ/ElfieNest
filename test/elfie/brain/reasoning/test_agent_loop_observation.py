"""Agent-loop action / observation / guard / judge decision records."""

from __future__ import annotations

from dataclasses import replace
from threading import Event
from typing import Tuple

import pytest

from elfie.brain.memory.memory_records import RecallBundle
from elfie.brain.observation import BrainObservation, ObservationStatus
from elfie.brain.reasoning.agent_loop_observations import (
    AgentLoopActionObservation,
    AgentLoopGuardObservation,
    AgentLoopGuardStopObservation,
    AgentLoopJudgeObservation,
    AgentLoopObservationRecorded,
    ModelCallObservation,
)
from elfie.brain.reasoning.decision_decoder import DecisionPlanDecoder
from elfie.brain.reasoning.memory_context import MemoryRecallResult
from elfie.brain.reasoning.reply_safety import ReplySafetyContext
from elfie.brain.reasoning.run import (
    _HONEST_EXTERNAL_BOUNDARY_REPLY,
    ReasoningBudget,
    ReasoningDepth,
    ReasoningRun,
    ReasoningStatus,
)
from test.elfie.brain.reasoning.test_reasoning import (
    SequenceCognitiveRuntime,
    _owner_cognitive_task,
)


class _CollectorSink:
    """Thread-safe in-memory sink recording every emitted observation."""

    def __init__(self) -> None:
        self._events: list[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        self._events.append(event)

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        return tuple(self._events)

    def of(self, boundary: str, kind: str) -> Tuple[BrainObservation, ...]:
        return tuple(
            event
            for event in self._events
            if (event.boundary, event.kind) == (boundary, kind)
        )


class _PinnedMemorySession:
    pinned_revision = 7

    def recall(self, query: str) -> MemoryRecallResult:
        return MemoryRecallResult(
            status="recalled",
            query=query,
            pinned_revision=self.pinned_revision,
            bundle=RecallBundle(recall_revision=self.pinned_revision),
        )


def _deliberate_recall_task(sink: _CollectorSink, runtime):
    session = _PinnedMemorySession()
    task = _owner_cognitive_task(
        depth=ReasoningDepth.DELIBERATE,
        memory_session=session,
        memory_revision=7,
    )

    def rebuild(observations):
        rendered = "\n".join(item.content for item in observations)
        return task.request.model_copy(
            update={"user_prompt": f"CURRENT_RUN_OBSERVATIONS:\n{rendered}"}
        )

    task = replace(task, context_request_builder=rebuild)
    return ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=5, max_model_calls=2, max_tool_calls=0),
        observation_sink=sink,
    ).run(task)


def test_deliberate_recall_loop_records_action_observation_guard_judge() -> None:
    sink = _CollectorSink()
    runtime = SequenceCognitiveRuntime(
        {
            "type": "recall_memory",
            "query": "主人纠正后的颜色偏好",
            "reason": "回答依赖持久偏好",
        },
        {"type": "answer", "content": "你纠正后的偏好是蓝色。"},
    )

    result = _deliberate_recall_task(sink, runtime)

    assert result.status is ReasoningStatus.COMPLETED

    actions = sink.of("reasoning.agent_loop", "action_decoded")
    assert len(actions) == 2
    recall = actions[0]
    assert recall.status is ObservationStatus.completed
    assert recall.turn_id == "turn-1"
    assert recall.frame_id == "frame-1"
    assert recall.cause_event_ids == ("event-1",)
    recall_payload = recall.payload
    assert isinstance(recall_payload, AgentLoopActionObservation)
    assert recall_payload.iteration_index == 1
    assert recall_payload.action_type == "RecallMemory"
    assert recall_payload.query == "主人纠正后的颜色偏好"
    assert recall_payload.recall_reason == "回答依赖持久偏好"
    answer_payload = actions[1].payload
    assert isinstance(answer_payload, AgentLoopActionObservation)
    assert answer_payload.action_type == "AnswerDraft"
    assert answer_payload.content == "你纠正后的偏好是蓝色。"

    observations = sink.of("reasoning.agent_loop", "observation")
    assert len(observations) == 1
    observation_payload = observations[0].payload
    assert isinstance(observation_payload, AgentLoopObservationRecorded)
    assert observation_payload.observation_kind == "memory"
    assert observation_payload.observation_status == "recalled"
    assert observation_payload.revision == 7

    guards = sink.of("reasoning.agent_loop", "guard")
    assert len(guards) == 2
    for guard in guards:
        guard_payload = guard.payload
        assert isinstance(guard_payload, AgentLoopGuardObservation)
        assert guard_payload.guard == "none"
        assert guard_payload.may_continue is True
        assert guard_payload.outcome == "continued"
        assert guard_payload.depth == "deliberate"
        assert guard_payload.cancelled is False
    assert [guard.payload.iteration_index for guard in guards] == [1, 2]
    assert guards[0].payload.max_model_calls == 2
    assert guards[1].payload.model_calls_used == 1
    assert guards[1].payload.model_calls_remaining == 1

    judges = sink.of("reasoning.completion", "judge")
    assert len(judges) == 1
    judge_payload = judges[0].payload
    assert isinstance(judge_payload, AgentLoopJudgeObservation)
    assert judge_payload.verdict == "accepted"
    assert judge_payload.action_type == "AnswerDraft"
    assert judge_payload.judge_reason is None
    assert judge_payload.external_claim_replaced is False

    # The committed model_call contract stays intact: same boundary, own
    # counter, untouched sequence numbering.
    model_calls = sink.of("reasoning.agent_loop", "model_call")
    assert [event.sequence for event in model_calls] == [1, 2]
    assert all(isinstance(event.payload, ModelCallObservation) for event in model_calls)
    # Decision records keep their own strictly increasing counter.
    decision_sequences = [
        event.sequence
        for event in sink.snapshot()
        if event.kind in {"action_decoded", "observation", "guard", "judge"}
    ]
    assert decision_sequences == sorted(decision_sequences)


def test_budget_exhausted_guard_stops_and_records_the_outcome() -> None:
    sink = _CollectorSink()
    recall_action = {
        "type": "recall_memory",
        "query": "继续找更多历史",
        "reason": "模型仍想继续",
    }
    runtime = SequenceCognitiveRuntime(recall_action, recall_action)

    result = _deliberate_recall_task(sink, runtime)

    assert result.status is ReasoningStatus.BUDGET_EXHAUSTED
    assert result.failure_reason == "model_call_budget_exhausted"

    guards = sink.of("reasoning.agent_loop", "guard")
    assert len(guards) == 3
    final_guard = guards[-1].payload
    assert isinstance(final_guard, AgentLoopGuardObservation)
    assert final_guard.guard == "model_budget"
    assert final_guard.may_continue is False
    assert final_guard.outcome == "stopped"
    assert final_guard.stop_reason == "model_call_budget_exhausted"
    assert final_guard.model_calls_used == 2
    assert final_guard.model_calls_remaining == 0

    stops = sink.of("reasoning.agent_loop", "guard_stop")
    assert len(stops) == 1
    stop_payload = stops[0].payload
    assert isinstance(stop_payload, AgentLoopGuardStopObservation)
    assert stop_payload.status == "budget_exhausted"
    assert stop_payload.reason == "model_call_budget_exhausted"
    assert stop_payload.model_calls == 2
    assert stop_payload.depth == "deliberate"


def test_completion_judge_records_revision_and_accepted_verdicts() -> None:
    sink = _CollectorSink()
    runtime = SequenceCognitiveRuntime(
        {"type": "answer", "content": "我已经创建提醒了。"},
        {"type": "answer", "content": "我现在不能创建提醒，但可以继续帮你梳理。"},
    )
    task = _owner_cognitive_task(depth=ReasoningDepth.DELIBERATE)

    def rebuild(observations):
        judge = "\n".join(item.content for item in observations)
        return task.request.model_copy(
            update={"user_prompt": f"CURRENT_MESSAGE:\n提醒我。\n{judge}"}
        )

    task = replace(task, context_request_builder=rebuild)
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=5, max_model_calls=2, max_tool_calls=0),
        observation_sink=sink,
    ).run(task)

    assert result.status is ReasoningStatus.COMPLETED
    judges = sink.of("reasoning.completion", "judge")
    assert len(judges) == 2
    first = judges[0].payload
    assert isinstance(first, AgentLoopJudgeObservation)
    assert first.verdict == "revision_required"
    assert first.judge_reason == "unsupported_external_completion_claim"
    assert first.revision_requested is True
    assert first.external_claim_replaced is False
    assert first.content == "我已经创建提醒了。"
    second = judges[1].payload
    assert isinstance(second, AgentLoopJudgeObservation)
    assert second.verdict == "accepted"
    assert second.judge_reason is None
    assert second.content == "我现在不能创建提醒，但可以继续帮你梳理。"

    judge_observations = sink.of("reasoning.agent_loop", "observation")
    assert judge_observations[0].payload.observation_kind == "judge"


def test_direct_fabrication_is_recorded_as_replaced_by_the_honest_reply() -> None:
    sink = _CollectorSink()
    runtime = SequenceCognitiveRuntime(
        {"type": "answer", "content": "我已经创建提醒了。"}
    )

    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
        observation_sink=sink,
    ).run(_owner_cognitive_task())

    assert result.status is ReasoningStatus.COMPLETED
    judges = sink.of("reasoning.completion", "judge")
    assert len(judges) == 1
    judge_payload = judges[0].payload
    assert isinstance(judge_payload, AgentLoopJudgeObservation)
    assert judge_payload.verdict == "accepted"
    assert judge_payload.judge_reason == "unsupported_external_completion_claim"
    assert judge_payload.revision_requested is False
    assert judge_payload.external_claim_replaced is True
    assert judge_payload.content == _HONEST_EXTERNAL_BOUNDARY_REPLY


def test_current_nest_rewrite_is_visible_on_the_accepted_judge_event() -> None:
    class HallucinatingOwnerRuntime(SequenceCognitiveRuntime):
        def __init__(self) -> None:
            super().__init__()
            self._calls = 0

        def generate(self, request):
            self._calls += 1
            from elfie.brain.reasoning.model_port import (
                ModelGenerationResult,
                StructuredOutputMode,
            )

            return ModelGenerationResult(
                text="我现在还不清楚今天精灵巢发生了什么呢，等我看看之后再告诉你哦。",
                selected_mode=StructuredOutputMode.PLAIN_TEXT,
                provider="fake",
                model_key="fake/schema",
            )

    sink = _CollectorSink()
    base = _owner_cognitive_task()
    task = replace(
        base,
        reply_safety_context=ReplySafetyContext(
            current_message="精灵巢今天发生了什么？",
        ),
    )
    result = ReasoningRun(
        model_port=HallucinatingOwnerRuntime(),
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
        observation_sink=sink,
    ).run(task)

    assert result.status is ReasoningStatus.COMPLETED
    assert result.decode.plan.intents[0].content == (
        "我现在还没有真实探索精灵巢，所以不知道今天那里发生了什么呢。"
    )
    judges = sink.of("reasoning.completion", "judge")
    assert len(judges) == 1
    judge_payload = judges[0].payload
    assert isinstance(judge_payload, AgentLoopJudgeObservation)
    assert judge_payload.verdict == "accepted"
    assert judge_payload.current_nest_sanitized is True


def test_depth_guard_stops_recall_memory_in_direct_runs() -> None:
    sink = _CollectorSink()
    runtime = SequenceCognitiveRuntime(
        {
            "type": "recall_memory",
            "query": "直接回合也想召回",
            "reason": "需要历史",
        }
    )

    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
        observation_sink=sink,
    ).run(_owner_cognitive_task())

    assert result.status is ReasoningStatus.SAFE_NOOP
    guards = sink.of("reasoning.agent_loop", "guard")
    depth_guards = [event for event in guards if event.payload.guard == "depth"]
    assert len(depth_guards) == 1
    depth_payload = depth_guards[0].payload
    assert isinstance(depth_payload, AgentLoopGuardObservation)
    assert depth_payload.may_continue is False
    assert depth_payload.outcome == "stopped"
    assert depth_payload.stop_reason == "recall_memory_not_allowed_in_direct"
    assert depth_payload.depth == "direct"

    stops = sink.of("reasoning.agent_loop", "guard_stop")
    assert len(stops) == 1
    assert stops[0].payload.status == "safe_noop"
    assert stops[0].payload.reason == "recall_memory_not_allowed_in_direct"


def test_cancellation_guard_stops_before_any_model_call() -> None:
    sink = _CollectorSink()
    cancelled = Event()
    cancelled.set()

    result = ReasoningRun(
        model_port=SequenceCognitiveRuntime(
            {"type": "answer", "content": "不会被调用"}
        ),
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
        observation_sink=sink,
    ).run(_owner_cognitive_task(), cancellation=cancelled)

    assert result.status is ReasoningStatus.CANCELLED
    guards = sink.of("reasoning.agent_loop", "guard")
    assert len(guards) == 1
    guard_payload = guards[0].payload
    assert isinstance(guard_payload, AgentLoopGuardObservation)
    assert guard_payload.guard == "cancellation"
    assert guard_payload.outcome == "stopped"
    assert guard_payload.cancelled is True
    assert guard_payload.stop_reason == "cancelled"
    stops = sink.of("reasoning.agent_loop", "guard_stop")
    assert len(stops) == 1
    assert stops[0].payload.status == "cancelled"


def test_decision_records_are_never_constructed_without_a_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError("decision record constructed without a sink")

    monkeypatch.setattr(BrainObservation, "__init__", _forbid_construction)
    for payload_type in (
        AgentLoopActionObservation,
        AgentLoopGuardObservation,
        AgentLoopGuardStopObservation,
        AgentLoopJudgeObservation,
        AgentLoopObservationRecorded,
    ):
        monkeypatch.setattr(payload_type, "__init__", _forbid_construction)

    runtime = SequenceCognitiveRuntime({"type": "answer", "content": " sink-free 完成"})
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
    ).run(_owner_cognitive_task())

    assert result.status is ReasoningStatus.COMPLETED
