from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Event

from elfie.brain.activity.system import (
    ActivityPreflightResult,
    ActivityPreflightStatus,
)
from elfie.brain.reasoning.decision_decoder import (
    DecisionDecodeSeed,
    DecisionPlanDecoder,
)
from elfie.brain.reasoning.model_port import (
    JsonSchemaDocument,
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelResponseMode,
    StructuredOutputMode,
)
from elfie.brain.reasoning.reply_safety import ReplySafetyContext
from elfie.brain.reasoning.run import (
    CognitiveStepKind,
    ReasoningBudget,
    ReasoningRun,
    ReasoningStatus,
)
from elfie.brain.reasoning.tool_port import ToolPort, ToolRequest, ToolResult
from elfie.brain.reasoning.worker import ReasoningTask
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    InternalScope,
    ResponseScope,
    SourceDomain,
)
from elfie.message_types import ElfieId, ErrorInfo, EventId, TurnId

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
DEADLINE = NOW + timedelta(seconds=30)


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
                    "type": "noop",
                    "intent_id": f"noop-{turn_id}",
                    "cause_event_ids": ["event-1"],
                    "dependency_ids": [],
                    "deadline": DEADLINE.isoformat(),
                    "cancel_policy": "if_not_started",
                    "reason": "verified",
                }
            ],
        }
    )


def _activity_plan_json(turn_id: str) -> str:
    step_deadline = NOW + timedelta(seconds=20)
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
                    "type": "activity",
                    "intent_id": f"activity-{turn_id}",
                    "cause_event_ids": ["event-1"],
                    "dependency_ids": [],
                    "deadline": DEADLINE.isoformat(),
                    "cancel_policy": "if_not_started",
                    "draft": {
                        "schema_version": 1,
                        "activity_id": "activity-1",
                        "goal": "整理线索",
                        "success_criteria": "内部步骤完成",
                        "steps": [
                            {
                                "step_id": "activity-step-1",
                                "ordinal": 0,
                                "kind": "internal",
                                "operation": "organize",
                                "deadline": step_deadline.isoformat(),
                                "scope": {
                                    "external_domain": None,
                                    "capability_revision": 1,
                                    "allowed_operations": ["organize"],
                                    "expires_at": step_deadline.isoformat(),
                                },
                            }
                        ],
                        "cause_event_ids": ["event-1"],
                        "idempotency_key": "activity-1:create",
                        "created_at": NOW.isoformat(),
                        "deadline": step_deadline.isoformat(),
                        "estimated_budget": 1.0,
                    },
                }
            ],
        }
    )


def _task(
    *,
    allowed_tools: tuple[str, ...] = (),
    tool_scope_id: ElfieId | None = None,
) -> ReasoningTask:
    request = ModelGenerationRequest(
        turn_id=TurnId("turn-1"),
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
            name="DecisionPlan", document={"type": "object"}
        ),
        allowed_tools=allowed_tools,
    )
    return ReasoningTask(
        request=request,
        tool_scope_id=tool_scope_id,
        seed=DecisionDecodeSeed(
            turn_id=TurnId("turn-1"),
            frame_id=EventId("frame-1"),
            context_revision=1,
            capability_revision=1,
            created_at=NOW,
            deadline=DEADLINE,
            cause_event_ids=(EventId("event-1"),),
        ),
    )


class SearchRuntime:
    def __init__(self) -> None:
        self.calls: list[ModelGenerationRequest] = []

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
        self.calls.append(request)
        text = (
            "[SEARCH]elfie nesting[/SEARCH]"
            if len(self.calls) == 1
            else _plan_json(str(request.turn_id))
        )
        return ModelGenerationResult(
            text=text,
            selected_mode=StructuredOutputMode.JSON_TEXT,
            provider="fake",
            model_key="fake/schema",
        )


class SearchTools:
    def __init__(self) -> None:
        self.requests: list[ToolRequest] = []

    def available_tool_keys(self) -> tuple[str, ...]:
        return ("web_search",)

    def execute(self, request: ToolRequest) -> ToolResult:
        self.requests.append(request)
        return ToolResult(
            tool_key=request.tool_key,
            ok=True,
            content="result: ElfieNest is a local embodied project",
            source_items=1,
        )


class StaticActivityPreflight:
    def __init__(self, status: ActivityPreflightStatus) -> None:
        self.status = status
        self.calls = 0

    def preflight(self, draft) -> ActivityPreflightResult:
        self.calls += 1
        reasons = ()
        if self.status is not ActivityPreflightStatus.VALIDATED:
            reasons = (ErrorInfo(code="target_unknown", message="请确认目标人"),)
        return ActivityPreflightResult(
            activity_id=draft.activity_id,
            status=self.status,
            checked_at=NOW,
            reasons=reasons,
        )


def test_reasoning_run_completes_tool_observation_loop_without_external_action() -> (
    None
):
    runtime = SearchRuntime()
    tools: ToolPort = SearchTools()
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        tool_port=tools,
        budget=ReasoningBudget(max_steps=8, max_model_calls=3, max_tool_calls=1),
    ).run(_task(allowed_tools=("web_search",)))

    assert result.status is ReasoningStatus.COMPLETED
    assert result.decode.plan.intents[0].type == "noop"
    assert len(runtime.calls) == 2
    assert len(tools.requests) == 1
    assert runtime.calls[0].allowed_tools == ()
    assert [step.kind for step in result.steps] == [
        CognitiveStepKind.MODEL,
        CognitiveStepKind.TOOL,
        CognitiveStepKind.OBSERVATION,
        CognitiveStepKind.MODEL,
        CognitiveStepKind.VERIFY,
    ]


def test_fast_owner_plain_text_never_enters_the_tool_loop() -> None:
    class PlainOwnerRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            return ModelGenerationResult(
                text="本地模型快路径已生效",
                selected_mode=StructuredOutputMode.PLAIN_TEXT,
                provider="fake",
                model_key="fake/schema",
            )

    base = _task()
    task = replace(
        base,
        request=base.request.model_copy(
            update={
                "source_domain": SourceDomain.COMMUNICATION,
                "interaction_scope": CommunicationScope(
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "response_scope": ResponseScope(
                    external_domain=ExternalExecutionDomain.COMMUNICATION,
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "reasoning_mode": "fast",
                "response_mode": ModelResponseMode.DIRECT_REPLY,
            }
        ),
        seed=base.seed.model_copy(
            update={
                "reply_channel_id": "chat",
                "reply_conversation_id": "owner:1",
            }
        ),
    )
    tools = SearchTools()

    result = ReasoningRun(
        model_port=PlainOwnerRuntime(),
        decoder=DecisionPlanDecoder(),
        tool_port=tools,
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
    ).run(task)

    assert result.decode.plan.intents[0].type == "message"
    assert result.decode.plan.intents[0].content == "本地模型快路径已生效"
    assert result.tool_calls == 0
    assert tools.requests == []


def test_fast_owner_reply_cannot_invent_current_nest_activity() -> None:
    class HallucinatingOwnerRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            return ModelGenerationResult(
                text="我现在还不清楚今天精灵巢发生了什么呢，等我看看之后再告诉你哦。",
                selected_mode=StructuredOutputMode.PLAIN_TEXT,
                provider="fake",
                model_key="fake/schema",
            )

    base = _task()
    task = replace(
        base,
        request=base.request.model_copy(
            update={
                "source_domain": SourceDomain.COMMUNICATION,
                "interaction_scope": CommunicationScope(
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "response_scope": ResponseScope(
                    external_domain=ExternalExecutionDomain.COMMUNICATION,
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "reasoning_mode": "fast",
                "response_mode": ModelResponseMode.DIRECT_REPLY,
            }
        ),
        seed=base.seed.model_copy(
            update={
                "reply_channel_id": "chat",
                "reply_conversation_id": "owner:1",
            }
        ),
        reply_safety_context=ReplySafetyContext(
            current_message="精灵巢今天发生了什么？",
        ),
    )

    result = ReasoningRun(
        model_port=HallucinatingOwnerRuntime(),
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
    ).run(task)

    assert result.decode.plan.intents[0].type == "message"
    assert result.decode.plan.intents[0].content == (
        "我现在还没有真实探索精灵巢，所以不知道今天那里发生了什么呢。"
    )
    assert any(
        step.kind is CognitiveStepKind.VERIFY
        and "current_nest_boundary" in step.summary
        for step in result.steps
    )


def test_fast_owner_reply_allows_current_nest_activity_with_explicit_observation() -> (
    None
):
    class ObservedOwnerRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            return ModelGenerationResult(
                text="我刚刚看到巢里的风铃被风吹响了。",
                selected_mode=StructuredOutputMode.PLAIN_TEXT,
                provider="fake",
                model_key="fake/schema",
            )

    base = _task()
    task = replace(
        base,
        request=base.request.model_copy(
            update={
                "source_domain": SourceDomain.COMMUNICATION,
                "interaction_scope": CommunicationScope(
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "response_scope": ResponseScope(
                    external_domain=ExternalExecutionDomain.COMMUNICATION,
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "reasoning_mode": "fast",
                "response_mode": ModelResponseMode.DIRECT_REPLY,
            }
        ),
        seed=base.seed.model_copy(
            update={
                "reply_channel_id": "chat",
                "reply_conversation_id": "owner:1",
            }
        ),
        reply_safety_context=ReplySafetyContext(
            current_message="精灵巢现在发生了什么？",
            has_current_nest_observation=True,
        ),
    )

    result = ReasoningRun(
        model_port=ObservedOwnerRuntime(),
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=3, max_model_calls=1, max_tool_calls=0),
    ).run(task)

    assert result.decode.plan.intents[0].content == "我刚刚看到巢里的风铃被风吹响了。"


def test_reasoning_run_attaches_host_activity_preflight_before_settlement() -> None:
    class ActivityRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            return ModelGenerationResult(
                text=_activity_plan_json(str(request.turn_id)),
                selected_mode=StructuredOutputMode.JSON_SCHEMA,
                provider="fake",
                model_key="fake/schema",
            )

    preflight = StaticActivityPreflight(ActivityPreflightStatus.VALIDATED)
    result = ReasoningRun(
        model_port=ActivityRuntime(),
        decoder=DecisionPlanDecoder(),
        activity_preflight=preflight,
    ).run(_task())

    assert result.status is ReasoningStatus.COMPLETED
    request = result.decode.plan.intents[0]
    assert request.type == "activity"
    assert request.preflight is not None
    assert request.preflight.status is ActivityPreflightStatus.VALIDATED
    assert preflight.calls == 1


def test_reasoning_run_returns_failed_preflight_as_same_run_observation() -> None:
    class ClarifyingRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            text = (
                _activity_plan_json(str(request.turn_id))
                if len(self.calls) == 1
                else _plan_json(str(request.turn_id))
            )
            return ModelGenerationResult(
                text=text,
                selected_mode=StructuredOutputMode.JSON_SCHEMA,
                provider="fake",
                model_key="fake/schema",
            )

    runtime = ClarifyingRuntime()
    preflight = StaticActivityPreflight(ActivityPreflightStatus.NEEDS_CLARIFICATION)
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        activity_preflight=preflight,
    ).run(_task())

    assert result.status is ReasoningStatus.COMPLETED
    assert result.decode.plan.intents[0].type == "noop"
    assert len(runtime.calls) == 2
    assert any(
        step.kind is CognitiveStepKind.OBSERVATION
        and step.status == "activity_preflight"
        for step in result.steps
    )
    assert "Activity Preflight Observation" in runtime.calls[1].user_prompt


def test_reasoning_run_accepts_structured_tool_step_for_json_model_runtimes() -> None:
    class StructuredSearchRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            text = (
                json.dumps(
                    {
                        "tool_key": "web_search",
                        "operation": "search",
                        "value": "elfie nesting",
                    }
                )
                if len(self.calls) == 1
                else _plan_json(str(request.turn_id))
            )
            return ModelGenerationResult(
                text=text,
                selected_mode=StructuredOutputMode.JSON_SCHEMA,
                provider="fake",
                model_key="fake/schema",
            )

    runtime = StructuredSearchRuntime()
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        tool_port=SearchTools(),
    ).run(_task(allowed_tools=("web_search",)))

    assert result.status is ReasoningStatus.COMPLETED
    assert result.tool_calls == 1
    assert len(runtime.calls) == 2


def test_reasoning_run_scopes_local_file_tool_to_the_owning_elfie() -> None:
    class FileRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            text = (
                "[READ_FILE]notes.txt[/READ_FILE]"
                if len(self.calls) == 1
                else _plan_json(str(request.turn_id))
            )
            return ModelGenerationResult(
                text=text,
                selected_mode=StructuredOutputMode.JSON_SCHEMA,
                provider="fake",
                model_key="fake/schema",
            )

    class FileTools(SearchTools):
        def available_tool_keys(self) -> tuple[str, ...]:
            return ("local_file",)

    tools = FileTools()
    result = ReasoningRun(
        model_port=FileRuntime(),
        decoder=DecisionPlanDecoder(),
        tool_port=tools,
    ).run(
        _task(
            allowed_tools=("local_file",),
            tool_scope_id=ElfieId("elfie-1"),
        )
    )

    assert result.status is ReasoningStatus.COMPLETED
    assert tools.requests[0].scope_id == ElfieId("elfie-1")
    assert tools.requests[0].resource_id == "notes.txt"


def test_reasoning_run_rejects_unauthorized_tool_and_returns_safe_noop() -> None:
    runtime = SearchRuntime()
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        tool_port=SearchTools(),
        budget=ReasoningBudget(max_steps=4, max_model_calls=2, max_tool_calls=1),
    ).run(_task())

    assert result.status is ReasoningStatus.TOOL_REJECTED
    assert result.decode.plan.intents[0].type == "noop"
    assert len(runtime.calls) == 1
    assert result.failure_reason == "tool_not_authorized"


def test_reasoning_run_does_not_treat_external_claims_as_tool_receipts() -> None:
    class ExternalClaimRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            self.calls.append(request)
            text = (
                "[SEND_MESSAGE]message was sent[/SEND_MESSAGE]"
                if len(self.calls) == 1
                else _plan_json(str(request.turn_id))
            )
            return ModelGenerationResult(
                text=text,
                selected_mode=StructuredOutputMode.JSON_SCHEMA,
                provider="fake",
                model_key="fake/schema",
            )

    tools = SearchTools()
    result = ReasoningRun(
        model_port=ExternalClaimRuntime(),
        decoder=DecisionPlanDecoder(),
        tool_port=tools,
    ).run(_task(allowed_tools=("web_search",)))

    assert result.status is ReasoningStatus.COMPLETED
    assert tools.requests == []


def test_reasoning_run_stops_at_budget_and_marks_failure() -> None:
    runtime = SearchRuntime()
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        tool_port=SearchTools(),
        budget=ReasoningBudget(max_steps=8, max_model_calls=1, max_tool_calls=1),
    ).run(_task(allowed_tools=("web_search",)))

    assert result.status is ReasoningStatus.BUDGET_EXHAUSTED
    assert result.decode.plan.intents[0].type == "noop"
    assert result.failure_reason == "model_call_budget_exhausted"
    assert len(result.steps) <= 8


def test_reasoning_run_honors_cancellation_before_model_call() -> None:
    runtime = SearchRuntime()
    cancelled = Event()
    cancelled.set()
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(max_steps=4, max_model_calls=2, max_tool_calls=1),
    ).run(_task(), cancellation=cancelled)

    assert result.status is ReasoningStatus.CANCELLED
    assert result.decode.plan.intents[0].type == "noop"
    assert runtime.calls == []


def test_reasoning_run_honors_local_deadline_before_model_call() -> None:
    runtime = SearchRuntime()
    result = ReasoningRun(
        model_port=runtime,
        decoder=DecisionPlanDecoder(),
        budget=ReasoningBudget(
            max_steps=4,
            max_model_calls=2,
            max_tool_calls=1,
            deadline_seconds=0,
        ),
    ).run(_task())

    assert result.status is ReasoningStatus.TIMED_OUT
    assert result.failure_reason == "deadline_exceeded"
    assert runtime.calls == []


def test_reasoning_run_exposes_model_unavailable_as_failure() -> None:
    class UnavailableRuntime(SearchRuntime):
        def capabilities(self) -> ModelGenerationCapabilities:
            raise RuntimeError("provider unavailable")

    result = ReasoningRun(
        model_port=UnavailableRuntime(),
        decoder=DecisionPlanDecoder(),
    ).run(_task())

    assert result.status is ReasoningStatus.FAILED
    assert result.failure_reason == "model_unavailable:RuntimeError"
    assert result.decode.plan.intents[0].type == "noop"


def test_reasoning_run_keeps_owner_chat_alive_when_model_generation_fails() -> None:
    class UnavailableOwnerRuntime(SearchRuntime):
        def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
            del request
            raise RuntimeError("provider unavailable")

    base = _task()
    task = replace(
        base,
        request=base.request.model_copy(
            update={
                "source_domain": SourceDomain.COMMUNICATION,
                "interaction_scope": CommunicationScope(
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "response_scope": ResponseScope(
                    external_domain=ExternalExecutionDomain.COMMUNICATION,
                    channel_id="chat",
                    conversation_id="owner:1",
                ),
                "response_mode": ModelResponseMode.DIRECT_REPLY,
            }
        ),
        seed=base.seed.model_copy(
            update={
                "reply_channel_id": "chat",
                "reply_conversation_id": "owner:1",
            }
        ),
    )

    result = ReasoningRun(
        model_port=UnavailableOwnerRuntime(),
        decoder=DecisionPlanDecoder(),
    ).run(task)

    assert result.status is ReasoningStatus.FAILED
    assert result.decode.plan.intents[0].type == "message"
    assert result.decode.plan.intents[0].content == "我收到你的消息了，正在想一想。"
    assert result.decode.report.fallback_reason == "model_unavailable:RuntimeError"


def test_reasoning_run_rejects_failed_tool_as_non_success() -> None:
    class FailedTools(SearchTools):
        def execute(self, request: ToolRequest) -> ToolResult:
            self.requests.append(request)
            return ToolResult(
                tool_key=request.tool_key,
                ok=False,
                content="denied",
                error=ErrorInfo(code="denied", message="not allowed"),
            )

    result = ReasoningRun(
        model_port=SearchRuntime(),
        decoder=DecisionPlanDecoder(),
        tool_port=FailedTools(),
        budget=ReasoningBudget(max_steps=8, max_model_calls=3, max_tool_calls=1),
    ).run(_task(allowed_tools=("web_search",)))

    assert result.status is ReasoningStatus.TOOL_FAILED
    assert result.decode.plan.intents[0].type == "noop"
