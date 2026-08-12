"""Bounded model--tool--observation reasoning owned by Brain.

The provider receives an inert request on every cognitive step.  Semantic tool
execution stays behind Brain's injected ``ToolPort`` and never becomes a
communication or body action.  A run always closes with either a verified
decision or an explicit safe NoOp result.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from threading import Event
from time import monotonic
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from pydantic import Field, JsonValue

from elfie.brain.activity.preflight import ActivityPreflightPort
from elfie.brain.activity.system import ActivityPreflightStatus
from elfie.brain.reasoning.decision_decoder import (
    DecisionDecodeMode,
    DecisionDecodeReport,
    DecisionDecodeResult,
    DecisionPlanDecoder,
)
from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionPlan,
    NoOpIntent,
    PersistentActivityRequest,
)
from elfie.brain.reasoning.model_port import (
    JsonSchemaDocument,
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelPort,
)
from elfie.brain.reasoning.tool_port import ToolPort, ToolRequest, ToolResult
from elfie.message_types import FrozenContractModel, IntentId, PlanId

if TYPE_CHECKING:
    from elfie.brain.reasoning.worker import ReasoningTaskView


@unique
class ReasoningStatus(str, Enum):
    """Terminal state of one bounded cognitive run."""

    COMPLETED = "completed"
    SAFE_NOOP = "safe_noop"
    TOOL_REJECTED = "tool_rejected"
    TOOL_FAILED = "tool_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    FAILED = "failed"


@unique
class CognitiveStepKind(str, Enum):
    """Publicly visible stages within one model turn."""

    MODEL = "model"
    TOOL = "tool"
    OBSERVATION = "observation"
    VERIFY = "verify"


class ReasoningBudget(FrozenContractModel):
    """Hard local bounds; no provider may extend them."""

    max_steps: int = Field(default=12, ge=1)
    max_model_calls: int = Field(default=4, ge=1)
    max_tool_calls: int = Field(default=2, ge=0)
    deadline_seconds: Optional[float] = Field(default=None, ge=0.0)


class CognitiveStep(FrozenContractModel):
    """Small redacted trace item suitable for Lab and diagnostics."""

    ordinal: int
    kind: CognitiveStepKind
    status: str
    summary: str
    tool_key: Optional[str] = None
    operation: Optional[str] = None
    ok: Optional[bool] = None


class ReasoningRunResult(FrozenContractModel):
    """Final structured decision plus explicit reasoning terminal evidence."""

    status: ReasoningStatus
    steps: Tuple[CognitiveStep, ...]
    model_calls: int
    tool_calls: int
    failure_reason: Optional[str]
    decode: DecisionDecodeResult


@dataclass(frozen=True)
class _ToolMarker:
    key: str
    operation: str
    value: str


class _ReasoningStop(RuntimeError):
    def __init__(self, status: ReasoningStatus, reason: str) -> None:
        self.status = status
        self.reason = reason
        super().__init__(reason)


_TOOL_MARKER = re.compile(
    r"\[(?P<kind>SEARCH|READ_FILE|LIST_FILES)\]\s*"
    r"(?P<value>.*?)\s*\[/\s*(?P=kind)\]",
    flags=re.IGNORECASE | re.DOTALL,
)
_TOOL_INSTRUCTIONS = (
    "\nBrain semantic tools are bounded and internal to cognition. "
    "If evidence is needed, emit exactly one marker: "
    "[SEARCH]query[/SEARCH], [READ_FILE]relative_path[/READ_FILE], or "
    "[LIST_FILES]relative_path[/LIST_FILES]. After the observation, return "
    "a DecisionPlan JSON object only. Never emit message or body tool calls."
)
_MAX_OBSERVATION_CHARS = 2400
_MAX_MODEL_SUMMARY_CHARS = 240
_TOOL_STEP_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "required": ["tool_key", "operation", "value"],
    "properties": {
        "tool_key": {"type": "string", "enum": ["web_search", "local_file"]},
        "operation": {"type": "string", "enum": ["search", "read", "list"]},
        "value": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}


class ReasoningRun:
    """Run a bounded cognitive loop for one already-admitted reasoning task."""

    def __init__(
        self,
        *,
        model_port: ModelPort,
        decoder: DecisionPlanDecoder,
        tool_port: ToolPort | None = None,
        activity_preflight: ActivityPreflightPort | None = None,
        budget: ReasoningBudget | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._model_port = model_port
        self._decoder = decoder
        self._tool_port = tool_port
        self._activity_preflight = activity_preflight
        self._budget = budget or ReasoningBudget()
        # The Brain's domain clock is intentionally not used for wall-clock
        # provider latency; the Coordinator owns the semantic Turn deadline.
        # This local budget is optional and uses a monotonic clock when set.
        del clock

    def run(
        self,
        task: ReasoningTaskView,
        *,
        cancellation: Event | None = None,
    ) -> ReasoningRunResult:
        """Execute until a verified plan or an explicit bounded failure."""
        steps: List[CognitiveStep] = []
        model_calls = 0
        tool_calls = 0
        capabilities: Optional[ModelGenerationCapabilities] = None
        last_generation: Optional[ModelGenerationResult] = None
        started_at = monotonic()
        turn_deadline_seconds = max(
            0.0,
            (task.request.deadline - task.request.created_at).total_seconds(),
        )
        deadline_seconds = (
            self._budget.deadline_seconds
            if self._budget.deadline_seconds is not None
            else turn_deadline_seconds
        )

        def guard(
            *, next_kind: CognitiveStepKind, model: bool = False, tool: bool = False
        ) -> None:
            if cancellation is not None and cancellation.is_set():
                raise _ReasoningStop(ReasoningStatus.CANCELLED, "cancelled")
            if monotonic() - started_at >= deadline_seconds:
                raise _ReasoningStop(ReasoningStatus.TIMED_OUT, "deadline_exceeded")
            if model and model_calls >= self._budget.max_model_calls:
                raise _ReasoningStop(
                    ReasoningStatus.BUDGET_EXHAUSTED,
                    "model_call_budget_exhausted",
                )
            if tool and tool_calls >= self._budget.max_tool_calls:
                raise _ReasoningStop(
                    ReasoningStatus.BUDGET_EXHAUSTED,
                    "tool_call_budget_exhausted",
                )
            if len(steps) >= self._budget.max_steps:
                raise _ReasoningStop(
                    ReasoningStatus.BUDGET_EXHAUSTED, "step_budget_exhausted"
                )
            del next_kind

        def add_step(
            kind: CognitiveStepKind,
            status: str,
            summary: str,
            *,
            tool_key: str | None = None,
            operation: str | None = None,
            ok: bool | None = None,
        ) -> None:
            if len(steps) >= self._budget.max_steps:
                raise _ReasoningStop(
                    ReasoningStatus.BUDGET_EXHAUSTED,
                    "step_budget_exhausted",
                )
            steps.append(
                CognitiveStep(
                    ordinal=len(steps) + 1,
                    kind=kind,
                    status=status,
                    summary=summary[:_MAX_OBSERVATION_CHARS],
                    tool_key=tool_key,
                    operation=operation,
                    ok=ok,
                )
            )

        try:
            capabilities = self._model_port.capabilities()
            current_prompt = task.request.user_prompt
            current_request = self._request(task.request, current_prompt)

            while True:
                guard(next_kind=CognitiveStepKind.MODEL, model=True)
                generation = self._model_port.generate(current_request)
                last_generation = generation
                model_calls += 1
                add_step(
                    CognitiveStepKind.MODEL,
                    "returned",
                    self._model_summary(generation.text),
                )
                marker = self._marker(generation.text)
                if marker is not None:
                    guard(next_kind=CognitiveStepKind.TOOL, tool=True)
                    try:
                        request = self._tool_request(task, marker)
                    except Exception as error:  # noqa: BLE001 - typed request boundary
                        raise _ReasoningStop(
                            ReasoningStatus.TOOL_REJECTED,
                            "tool_request_invalid",
                        ) from error
                    self._authorize_tool(task.request, request)
                    if self._tool_port is None:
                        raise _ReasoningStop(
                            ReasoningStatus.TOOL_REJECTED,
                            "tool_port_unavailable",
                        )
                    available = tuple(
                        str(key) for key in self._tool_port.available_tool_keys()
                    )
                    if request.tool_key not in available:
                        raise _ReasoningStop(
                            ReasoningStatus.TOOL_REJECTED,
                            "tool_not_available",
                        )
                    tool_calls += 1
                    add_step(
                        CognitiveStepKind.TOOL,
                        "requested",
                        f"{request.tool_key}:{request.operation}",
                        tool_key=request.tool_key,
                        operation=request.operation,
                    )
                    try:
                        tool_result = self._tool_port.execute(request)
                    except Exception as error:  # noqa: BLE001 - ToolPort boundary
                        raise _ReasoningStop(
                            ReasoningStatus.TOOL_FAILED,
                            f"tool_execution_error:{type(error).__name__}",
                        ) from error
                    if not tool_result.ok:
                        add_step(
                            CognitiveStepKind.OBSERVATION,
                            "failed",
                            self._observation_summary(tool_result),
                            tool_key=tool_result.tool_key,
                            operation=request.operation,
                            ok=False,
                        )
                        raise _ReasoningStop(
                            ReasoningStatus.TOOL_FAILED,
                            "tool_result_failed",
                        )
                    add_step(
                        CognitiveStepKind.OBSERVATION,
                        "received",
                        self._observation_summary(tool_result),
                        tool_key=tool_result.tool_key,
                        operation=request.operation,
                        ok=True,
                    )
                    current_prompt = self._observation_prompt(
                        current_prompt,
                        request,
                        tool_result,
                    )
                    current_request = self._request(
                        task.request,
                        current_prompt,
                        final_schema=True,
                    )
                    continue

                def repair(raw_text: str, errors: tuple[str, ...]) -> str:
                    nonlocal model_calls, last_generation
                    guard(next_kind=CognitiveStepKind.MODEL, model=True)
                    repair_prompt = (
                        "Repair the following invalid DecisionPlan JSON. Return JSON only.\n"
                        f"Errors: {'; '.join(errors)}\nRaw output:\n{raw_text}"
                    )
                    repaired_request = self._request(
                        task.request,
                        repair_prompt,
                        final_schema=True,
                    )
                    repaired = self._model_port.generate(repaired_request)
                    last_generation = repaired
                    model_calls += 1
                    add_step(
                        CognitiveStepKind.MODEL,
                        "repair_returned",
                        self._model_summary(repaired.text),
                    )
                    return repaired.text

                decode = self._decoder.decode(
                    seed=task.seed,
                    generation=generation,
                    capabilities=capabilities,
                    repair_callback=None if capabilities.plain_text_only else repair,
                )
                plan, preflight_observation = self._preflight_activities(decode.plan)
                if preflight_observation is not None:
                    add_step(
                        CognitiveStepKind.OBSERVATION,
                        "activity_preflight",
                        preflight_observation,
                        operation="activity_preflight",
                        ok=False,
                    )
                    current_prompt = (
                        f"{current_prompt}\n\n"
                        "[Activity Preflight Observation]\n"
                        f"{preflight_observation}\n"
                        "Resolve the missing facts now. Return either a corrected "
                        "DecisionPlan or a scoped clarification message; do not defer "
                        "clarification to the future Activity."
                    )
                    current_request = self._request(
                        task.request,
                        current_prompt,
                        final_schema=True,
                    )
                    continue
                if plan is not decode.plan:
                    decode = decode.model_copy(update={"plan": plan})
                if decode.report.fallback_reason is not None:
                    add_step(
                        CognitiveStepKind.VERIFY,
                        "degraded",
                        decode.report.fallback_reason,
                    )
                    return ReasoningRunResult(
                        status=ReasoningStatus.SAFE_NOOP,
                        steps=tuple(steps),
                        model_calls=model_calls,
                        tool_calls=tool_calls,
                        failure_reason=decode.report.fallback_reason,
                        decode=decode,
                    )
                add_step(CognitiveStepKind.VERIFY, "accepted", "DecisionPlan verified")
                return ReasoningRunResult(
                    status=ReasoningStatus.COMPLETED,
                    steps=tuple(steps),
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                    failure_reason=None,
                    decode=decode,
                )
        except _ReasoningStop as stopped:
            return self._failure(
                task=task,
                status=stopped.status,
                reason=stopped.reason,
                steps=steps,
                model_calls=model_calls,
                tool_calls=tool_calls,
                capabilities=capabilities,
                generation=last_generation,
            )
        except Exception as error:  # noqa: BLE001 - model boundary
            return self._failure(
                task=task,
                status=ReasoningStatus.FAILED,
                reason=f"model_unavailable:{type(error).__name__}",
                steps=steps,
                model_calls=model_calls,
                tool_calls=tool_calls,
                capabilities=capabilities,
                generation=last_generation,
            )

    def _request(
        self,
        base: ModelGenerationRequest,
        user_prompt: str,
        *,
        final_schema: bool = False,
    ) -> ModelGenerationRequest:
        response_schema = base.response_schema
        if not final_schema:
            response_schema = JsonSchemaDocument(
                name="ReasoningStep",
                document={
                    "anyOf": [
                        dict(base.response_schema.document),
                        _TOOL_STEP_SCHEMA,
                    ]
                },
            )
        return base.model_copy(
            update={
                "system_prompt": base.system_prompt + _TOOL_INSTRUCTIONS,
                "user_prompt": user_prompt,
                "response_schema": response_schema,
                # Tool execution is owned by this loop; do not activate a
                # second provider/runtime-side tool loop for the same Turn.
                "allowed_tools": ()
                if self._tool_port is not None
                else base.allowed_tools,
            }
        )

    @staticmethod
    def _marker(text: str) -> _ToolMarker | None:
        match = _TOOL_MARKER.search(text)
        if match is not None:
            kind = match.group("kind").upper()
            value = match.group("value").strip()
            if kind == "SEARCH":
                return _ToolMarker("web_search", "search", value)
            if kind == "READ_FILE":
                return _ToolMarker("local_file", "read", value)
            return _ToolMarker("local_file", "list", value)
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        key = parsed.get("tool_key")
        operation = parsed.get("operation")
        value = parsed.get("value")
        if (
            not isinstance(key, str)
            or not isinstance(operation, str)
            or not isinstance(value, str)
        ):
            return None
        if key == "web_search" and operation == "search":
            return _ToolMarker(key, operation, value)
        if key == "local_file" and operation in {"read", "list"}:
            return _ToolMarker(key, operation, value)
        return None

    @staticmethod
    def _tool_request(task: ReasoningTaskView, marker: _ToolMarker) -> ToolRequest:
        if marker.key == "web_search":
            return ToolRequest(
                tool_key="web_search", operation="search", query=marker.value
            )
        scope_id = getattr(task, "tool_scope_id", None)
        return ToolRequest(
            scope_id=scope_id,
            tool_key="local_file",
            operation=marker.operation,  # type: ignore[arg-type]
            resource_id=marker.value,
        )

    @staticmethod
    def _authorize_tool(request: ModelGenerationRequest, tool: ToolRequest) -> None:
        if tool.tool_key not in request.allowed_tools:
            raise _ReasoningStop(
                ReasoningStatus.TOOL_REJECTED,
                "tool_not_authorized",
            )

    @staticmethod
    def _model_summary(text: str) -> str:
        compact = " ".join(text.split())
        return compact[:_MAX_MODEL_SUMMARY_CHARS] or "empty model output"

    @staticmethod
    def _observation_summary(result: ToolResult) -> str:
        return result.content[:_MAX_OBSERVATION_CHARS] or "empty tool observation"

    @staticmethod
    def _observation_prompt(
        original_prompt: str,
        request: ToolRequest,
        result: ToolResult,
    ) -> str:
        return (
            f"{original_prompt}\n\n"
            f"[Observation from {request.tool_key}:{request.operation}]\n"
            f"{result.content[:_MAX_OBSERVATION_CHARS]}\n"
            "Use this evidence and return a DecisionPlan JSON object only."
        )

    def _preflight_activities(
        self,
        plan: DecisionPlan,
    ) -> tuple[DecisionPlan, str | None]:
        """Validate Activity drafts before the ReasoningRun may settle."""
        requests = tuple(
            intent
            for intent in plan.intents
            if isinstance(intent, PersistentActivityRequest)
        )
        if not requests:
            return plan, None
        if self._activity_preflight is None:
            return plan, json.dumps(
                {
                    "status": ActivityPreflightStatus.NEEDS_CLARIFICATION.value,
                    "reasons": [
                        {
                            "code": "activity_preflight_unavailable",
                            "message": "Activity validation is unavailable",
                        }
                    ],
                },
                ensure_ascii=False,
            )

        validated: dict[str, object] = {}
        failures: list[dict[str, object]] = []
        for request in requests:
            result = self._activity_preflight.preflight(request.draft)
            if result.status is ActivityPreflightStatus.VALIDATED:
                validated[str(request.draft.activity_id)] = result
                continue
            failures.append(
                {
                    "activity_id": str(request.draft.activity_id),
                    "status": result.status.value,
                    "reasons": [
                        reason.model_dump(mode="json") for reason in result.reasons
                    ],
                }
            )
        if failures:
            return plan, json.dumps(failures, ensure_ascii=False)

        intents = tuple(
            intent.model_copy(
                update={"preflight": validated[str(intent.draft.activity_id)]}
            )
            if isinstance(intent, PersistentActivityRequest)
            else intent
            for intent in plan.intents
        )
        return plan.model_copy(update={"intents": intents}), None

    def _failure(
        self,
        *,
        task: ReasoningTaskView,
        status: ReasoningStatus,
        reason: str,
        steps: List[CognitiveStep],
        model_calls: int,
        tool_calls: int,
        capabilities: Optional[ModelGenerationCapabilities],
        generation: Optional[ModelGenerationResult],
    ) -> ReasoningRunResult:
        decode = self._safe_noop(
            task,
            reason,
            capabilities=capabilities,
            generation=generation,
        )
        if len(steps) < self._budget.max_steps:
            steps.append(
                CognitiveStep(
                    ordinal=len(steps) + 1,
                    kind=CognitiveStepKind.VERIFY,
                    status="safe_noop",
                    summary=reason,
                )
            )
        return ReasoningRunResult(
            status=status,
            steps=tuple(steps),
            model_calls=model_calls,
            tool_calls=tool_calls,
            failure_reason=reason,
            decode=decode,
        )

    @staticmethod
    def _safe_noop(
        task: ReasoningTaskView,
        reason: str,
        *,
        capabilities: Optional[ModelGenerationCapabilities],
        generation: Optional[ModelGenerationResult],
    ) -> DecisionDecodeResult:
        seed = task.seed
        plan = DecisionPlan(
            plan_id=PlanId(f"reasoning-noop-{seed.turn_id}"),
            turn_id=seed.turn_id,
            frame_id=seed.frame_id,
            context_revision=seed.context_revision,
            capability_revision=seed.capability_revision,
            created_at=seed.created_at,
            deadline=seed.deadline,
            cause_event_ids=seed.cause_event_ids,
            intents=(
                NoOpIntent(
                    type="noop",
                    intent_id=IntentId(f"reasoning-noop-intent-{seed.turn_id}"),
                    cause_event_ids=seed.cause_event_ids,
                    dependency_ids=(),
                    deadline=seed.deadline,
                    cancel_policy=CancelPolicy.IF_NOT_STARTED,
                    reason=reason,
                ),
            ),
        )
        return DecisionDecodeResult(
            plan=plan,
            report=DecisionDecodeReport(
                selected_mode=DecisionDecodeMode.JSON_TEXT,
                validation_errors=(),
                repair_count=0,
                fallback_reason=reason,
                model_id=(
                    generation.model_key
                    if generation is not None
                    else capabilities.model_key
                    if capabilities is not None
                    else "unavailable"
                ),
                provider=(
                    generation.provider
                    if generation is not None
                    else capabilities.provider
                    if capabilities is not None
                    else "brain"
                ),
                token_count=(
                    generation.token_count if generation is not None else None
                ),
                latency_ms=(generation.latency_ms if generation is not None else None),
            ),
        )


__all__ = (
    "CognitiveStep",
    "CognitiveStepKind",
    "ReasoningBudget",
    "ReasoningRun",
    "ReasoningRunResult",
    "ReasoningStatus",
)
