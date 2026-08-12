from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from threading import Event

from elfie.brain.cortical_worker import CorticalTask
from elfie.brain.decision_decoder import DecisionDecodeSeed, DecisionPlanDecoder
from elfie.brain.perception_types import InternalScope, ResponseScope, SourceDomain
from elfie.brain.reasoning import (
    CognitiveStepKind,
    ReasoningBudget,
    ReasoningRun,
    ReasoningStatus,
)
from elfie.brain.runtime_port import (
    JsonSchemaDocument,
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.brain.tool_port import ToolPort, ToolRequest, ToolResult
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


def _task(
    *,
    allowed_tools: tuple[str, ...] = (),
    tool_scope_id: ElfieId | None = None,
) -> CorticalTask:
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
    return CorticalTask(
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
