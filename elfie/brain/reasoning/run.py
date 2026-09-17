"""Bounded model--tool--observation reasoning owned by Brain.

The provider receives an inert request on every cognitive step.  Semantic tool
execution stays behind Brain's injected ``ToolPort`` and never becomes a
communication or body action.  A run always closes with either a verified
decision or an explicit safe failure result.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum, unique
from threading import Event
from time import monotonic
from typing import TYPE_CHECKING, Callable, List, Literal, Optional, Tuple, cast

from pydantic import Field, JsonValue

from elfie.brain.activity.preflight import ActivityPreflightPort
from elfie.brain.activity.system import ActivityPreflightStatus
from elfie.brain.observation import (
    BrainObservation,
    BrainObservationSink,
    ObservationError,
    ObservationStatus,
)
from elfie.brain.reasoning.agent_loop_observations import (
    AgentLoopActionObservation,
    AgentLoopGuardObservation,
    AgentLoopGuardStopObservation,
    AgentLoopJudgeObservation,
    AgentLoopObservationRecorded,
    AgentLoopRunFailedObservation,
    ModelCallObservation,
)
from elfie.brain.reasoning.decision_decoder import (
    DecisionDecodeMode,
    DecisionDecodeReport,
    DecisionDecodeResult,
    DecisionPlanDecoder,
)
from elfie.brain.reasoning.decision_types import (
    AnswerDraft,
    CancelPolicy,
    ClarificationDraft,
    CognitiveAction,
    DecisionIntent,
    DecisionPlan,
    MessageIntent,
    NoOpDraft,
    NoOpIntent,
    PersistentActivityRequest,
    RecallMemory,
)
from elfie.brain.reasoning.memory_compiler import (
    compile_recall_bundle,
    recall_memory_reference_ids,
)
from elfie.brain.reasoning.model_port import (
    JsonSchemaDocument,
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelPort,
    ModelResponseMode,
)
from elfie.brain.reasoning.reply_safety import (
    TRUSTED_OWNER_FAILURE_REPLY,
    sanitize_direct_owner_reply,
)
from elfie.brain.reasoning.skill_port import (
    SKILL_LOADER_NAME,
    SkillLoadCall,
)
from elfie.brain.reasoning.tool_port import (
    ToolCall,
    ToolOperation,
    ToolPort,
    ToolRequest,
    ToolResult,
)
from elfie.message_types import FrozenContractModel, IntentId, PlanId

if TYPE_CHECKING:
    from elfie.brain.reasoning.worker import ReasoningTaskView


_TOOL_OPERATIONS: dict[str, ToolOperation] = {
    "search": "search",
    "read": "read",
    "list": "list",
}


def _json_int(value: JsonValue, default: int) -> int:
    if isinstance(value, (str, int, float)):
        return int(value)
    return default


def _tool_operation(value: JsonValue, default: ToolOperation) -> ToolOperation:
    if isinstance(value, str):
        return _TOOL_OPERATIONS.get(value, default)
    return default


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
class ReasoningDepth(str, Enum):
    """Cognitive depth selected for one Turn before the loop starts."""

    DIRECT = "direct"
    DELIBERATE = "deliberate"


@unique
class CognitiveStepKind(str, Enum):
    """Publicly visible stages within one model turn."""

    MODEL = "model"
    SKILL = "skill"
    TOOL = "tool"
    OBSERVATION = "observation"
    VERIFY = "verify"


ReasoningPlanStepKind = Literal[
    "recall_evidence",
    "verify_draft",
    "correct_draft",
    "form_reply",
]


class ReasoningPlan(FrozenContractModel):
    """A lazily-created 1--3 step plan that exists only inside one Run."""

    trigger: Literal["additional_observation", "revision_required"]
    steps: Tuple[ReasoningPlanStepKind, ...] = Field(min_length=1, max_length=3)


class ReasoningBudget(FrozenContractModel):
    """Per-Run admission bounds with a host-owned plan expansion."""

    # ``max_steps`` is an optional last-resort loop fuse.  Model calls and
    # tool calls are the real budgets; ordinary Runs derive their termination
    # from those counters plus the deadline instead of competing with another
    # fixed step number.
    max_steps: Optional[int] = Field(default=None, ge=1)
    # Before a host-owned ReasoningPlan exists, this is the active model-call
    # limit.  It remains a hard limit for callers that do not opt into plan
    # expansion, preserving the existing explicit-budget contract.
    max_model_calls: int = Field(default=4, ge=1)
    # Once Brain creates a valid short plan, the Run may expand up to this
    # second ceiling.  It never resets calls already spent and never applies
    # to DIRECT because DIRECT never creates a plan.
    max_planned_model_calls: Optional[int] = Field(default=None, ge=1)
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


class CurrentRunObservation(FrozenContractModel):
    """Structured same-Run material consumed by the one Context Engine path."""

    kind: str
    status: str
    content: str
    source_ids: Tuple[str, ...] = ()
    revision: Optional[int] = Field(default=None, ge=0)


class ReasoningRunResult(FrozenContractModel):
    """Final structured decision plus explicit reasoning terminal evidence."""

    status: ReasoningStatus
    steps: Tuple[CognitiveStep, ...]
    model_calls: int
    tool_calls: int
    failure_reason: Optional[str]
    skill_calls: int = 0
    decode: DecisionDecodeResult
    plan: Optional[ReasoningPlan] = None


class _ReasoningStop(RuntimeError):
    def __init__(self, status: ReasoningStatus, reason: str) -> None:
        self.status = status
        self.reason = reason
        super().__init__(reason)


_MAX_OBSERVATION_CHARS = 2400
_MAX_MODEL_SUMMARY_CHARS = 240
_MAX_ERROR_CHARS = 240
_SHORT_PLAN_OBSERVATION_KIND = "short_plan"
_HONEST_EXTERNAL_BOUNDARY_REPLY = (
    "我目前没有执行或确认任何外部操作；如果你愿意，我可以先就现有信息继续聊。"
)
_UNSUPPORTED_EXTERNAL_COMPLETION = re.compile(
    r"(?:已经|已|刚刚).{0,16}(?:发送|发出|创建.{0,6}提醒|设好.{0,6}提醒|"
    r"搜索|查完|读取.{0,6}文件|写入.{0,6}文件|移动|执行完|完成任务)|"
    r"\bI\s+(?:have\s+)?(?:sent|searched|created\s+(?:the\s+)?reminder|"
    r"read\s+the\s+file|wrote\s+the\s+file|completed\s+the\s+task)\b",
    flags=re.IGNORECASE | re.DOTALL,
)


def _with_brain_owned_schema_protocol(
    system_prompt: str,
    response_schema: JsonSchemaDocument,
    capabilities: ModelGenerationCapabilities | None,
) -> str:
    """Keep JSON-mode schema guidance inside Brain's runtime protocol.

    Native schema/tool-call providers receive the typed schema out of band.
    JSON-mode providers need the schema in text, but Provider adapters are not
    allowed to mutate a Brain-owned system prompt.  Insert it immediately
    before dynamic Brain state so the four-block fixed prefix stays byte-stable.
    """

    if (
        capabilities is None
        or capabilities.supports_json_schema
        or capabilities.supports_tool_calling
        or not capabilities.supports_json_mode
    ):
        return system_prompt
    instruction = "RESPONSE_SCHEMA_JSON:\n" + json.dumps(
        response_schema.document,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    state_marker = "\n\n[CURRENT_BRAIN_STATE]\n"
    if state_marker in system_prompt:
        protocol, state = system_prompt.split(state_marker, 1)
        return f"{protocol}\n\n{instruction}{state_marker}{state}"
    return f"{system_prompt}\n\n{instruction}"


def _new_recall_plan() -> ReasoningPlan:
    """Describe the second dependent evidence step without reading content."""
    return ReasoningPlan(
        trigger="additional_observation",
        steps=("recall_evidence", "form_reply"),
    )


def _new_revision_plan() -> ReasoningPlan:
    """Describe one host-requested correction without exposing hidden thoughts."""
    return ReasoningPlan(
        trigger="revision_required",
        steps=("verify_draft", "correct_draft"),
    )


def _replace_plan_observation(
    observations: List[CurrentRunObservation],
    plan: ReasoningPlan,
) -> None:
    """Expose only the current plan state to the next Context Engine pass."""
    observations[:] = [
        observation
        for observation in observations
        if observation.kind != _SHORT_PLAN_OBSERVATION_KIND
    ]
    rendered_steps = "; ".join(
        f"{ordinal}:{kind}" for ordinal, kind in enumerate(plan.steps, start=1)
    )
    observations.append(
        CurrentRunObservation(
            kind=_SHORT_PLAN_OBSERVATION_KIND,
            status="active",
            content=f"trigger={plan.trigger}; steps={rendered_steps}",
        )
    )


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
        observation_sink: BrainObservationSink | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._model_port = model_port
        self._decoder = decoder
        self._tool_port = tool_port
        self._activity_preflight = activity_preflight
        self._budget = budget or ReasoningBudget()
        # Agent-loop model calls observe through this sink when one is wired;
        # bridge and context-engine emits live in their owning components.
        self._observation_sink = observation_sink
        # Monotonic per-Run sequence for reasoning.agent_loop observations.
        # One ReasoningRun serves one run() call on the worker thread, so an
        # unsynchronized counter is sufficient.
        self._observation_sequence = 0
        # Decision records keep their own counter: merging it into the
        # model_call sequence would shift the committed model_call numbering.
        self._decision_sequence = 0
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
        skill_calls = 0
        capabilities: Optional[ModelGenerationCapabilities] = None
        last_generation: Optional[ModelGenerationResult] = None
        run_observations: List[CurrentRunObservation] = []
        reasoning_plan: Optional[ReasoningPlan] = None
        active_model_limit = self._budget.max_model_calls
        memory_reference_ids = list(getattr(task, "memory_reference_ids", ()))
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

        def activate_plan_budget() -> None:
            """Expand only after Brain has created a host-owned plan."""
            nonlocal active_model_limit
            planned_limit = self._budget.max_planned_model_calls
            if planned_limit is not None:
                active_model_limit = max(active_model_limit, planned_limit)

        def step_limit_reached() -> bool:
            limit = self._budget.max_steps
            return limit is not None and len(steps) >= limit

        def record_observation(
            *,
            kind: str,
            status: str,
            content: str,
            source_ids: Tuple[str, ...] = (),
            revision: Optional[int] = None,
        ) -> None:
            """Append one Run observation and record the append event."""
            append_started = monotonic() if self._observation_sink is not None else 0.0
            observation = CurrentRunObservation(
                kind=kind,
                status=status,
                content=content,
                source_ids=source_ids,
                revision=revision,
            )
            run_observations.append(observation)
            append_duration_ms = (
                round((monotonic() - append_started) * 1000.0, 2)
                if self._observation_sink is not None
                else 0.0
            )
            self._emit_observation_recorded(
                task=task,
                observation=observation,
                iteration_index=model_calls + 1,
                duration_ms=append_duration_ms,
            )

        def guard(
            *, next_kind: CognitiveStepKind, model: bool = False, tool: bool = False
        ) -> None:
            fired: Optional[Tuple[str, ReasoningStatus, str]] = None
            if cancellation is not None and cancellation.is_set():
                fired = ("cancellation", ReasoningStatus.CANCELLED, "cancelled")
            elif monotonic() - started_at >= deadline_seconds:
                fired = ("deadline", ReasoningStatus.TIMED_OUT, "deadline_exceeded")
            elif model and model_calls >= active_model_limit:
                fired = (
                    "model_budget",
                    ReasoningStatus.BUDGET_EXHAUSTED,
                    "model_call_budget_exhausted",
                )
            elif tool and tool_calls >= self._budget.max_tool_calls:
                fired = (
                    "tool_budget",
                    ReasoningStatus.BUDGET_EXHAUSTED,
                    "tool_call_budget_exhausted",
                )
            elif step_limit_reached():
                fired = (
                    "steps",
                    ReasoningStatus.BUDGET_EXHAUSTED,
                    "step_budget_exhausted",
                )
            self._emit_guard(
                task=task,
                fired=fired,
                iteration_index=model_calls + 1,
                model_calls_used=model_calls,
                active_model_limit=active_model_limit,
                tool_calls_used=tool_calls,
                started_at=started_at,
                deadline_seconds=deadline_seconds,
                cancelled=cancellation is not None and cancellation.is_set(),
            )
            if fired is not None:
                raise _ReasoningStop(fired[1], fired[2])
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
            if step_limit_reached():
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
            context_request_builder = getattr(task, "context_request_builder", None)

            def rebuild_request(
                *,
                final_schema: bool = False,
                legacy_prompt: str | None = None,
            ) -> ModelGenerationRequest:
                nonlocal current_prompt
                if context_request_builder is not None:
                    base = context_request_builder(tuple(run_observations))
                    current_prompt = base.user_prompt
                else:
                    base = task.request
                    if legacy_prompt is not None:
                        current_prompt = legacy_prompt
                return self._request(
                    base,
                    current_prompt,
                    final_schema=final_schema,
                    capabilities=capabilities,
                    allow_deliberate_tools=(
                        getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
                        is ReasoningDepth.DELIBERATE
                    ),
                )

            current_request = rebuild_request()

            while True:
                guard(next_kind=CognitiveStepKind.MODEL, model=True)
                remaining_seconds = deadline_seconds - (monotonic() - started_at)
                generation_request = current_request.model_copy(
                    update={
                        "timeout_seconds": max(
                            0.001,
                            remaining_seconds,
                        )
                    }
                )
                generation = self._observed_generate(
                    generation_request,
                    iteration_index=model_calls + 1,
                    capabilities=capabilities,
                )
                last_generation = generation
                model_calls += 1
                add_step(
                    CognitiveStepKind.MODEL,
                    "returned",
                    self._model_summary(generation.text),
                )
                if generation.skill_calls or generation.tool_calls:
                    generated_observations: list[str] = []
                    for skill_call in generation.skill_calls:
                        skill_calls += 1
                        skill = self._load_skill(current_request, task, skill_call)
                        if skill is None:
                            raise _ReasoningStop(
                                ReasoningStatus.TOOL_REJECTED,
                                "skill_not_available",
                            )
                        skill_content = skill.instructions[:_MAX_OBSERVATION_CHARS]
                        add_step(
                            CognitiveStepKind.SKILL,
                            "loaded",
                            f"{skill.name} ({skill_call.call_id})",
                            tool_key=SKILL_LOADER_NAME,
                            operation="load",
                            ok=True,
                        )
                        record_observation(
                            kind="skill",
                            status="loaded",
                            content=(
                                f"name={skill.name}; description={skill.description}; "
                                f"instructions={skill_content}"
                            ),
                            source_ids=(f"skill:{skill.name}",),
                        )
                        generated_observations.append(
                            self._skill_observation_prompt(
                                current_prompt,
                                skill.name,
                                skill.instructions,
                            )
                        )
                    for tool_call in generation.tool_calls:
                        guard(next_kind=CognitiveStepKind.TOOL, tool=True)
                        try:
                            request = self._tool_request_from_call(task, tool_call)
                        except Exception as error:  # noqa: BLE001 - typed boundary
                            raise _ReasoningStop(
                                ReasoningStatus.TOOL_REJECTED,
                                "tool_request_invalid",
                            ) from error
                        self._authorize_tool(current_request, request)
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
                            f"{tool_call.tool_key} ({tool_call.call_id})",
                            tool_key=tool_call.tool_key,
                            operation=request.operation,
                        )
                        try:
                            tool_result = self._tool_port.execute(request)
                        except Exception as error:  # noqa: BLE001 - ToolPort boundary
                            raise _ReasoningStop(
                                ReasoningStatus.TOOL_FAILED,
                                f"tool_execution_error:{type(error).__name__}",
                            ) from error
                        summary = self._observation_summary(tool_result)
                        if not tool_result.ok:
                            add_step(
                                CognitiveStepKind.OBSERVATION,
                                "failed",
                                summary,
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
                            summary,
                            tool_key=tool_result.tool_key,
                            operation=request.operation,
                            ok=True,
                        )
                        record_observation(
                            kind="tool",
                            status="received",
                            content=summary,
                            source_ids=(f"{request.tool_key}:{request.operation}",),
                        )
                        generated_observations.append(
                            self._observation_prompt(
                                current_prompt,
                                request,
                                tool_result,
                            )
                        )
                    current_request = rebuild_request(
                        final_schema=True,
                        legacy_prompt=generated_observations[-1]
                        if generated_observations
                        else None,
                    )
                    continue
                if current_request.response_mode is ModelResponseMode.DIRECT_REPLY:
                    decode_started = (
                        monotonic() if self._observation_sink is not None else 0.0
                    )

                    def decode_elapsed_ms(
                        started: float = decode_started,
                    ) -> float:
                        return (
                            round((monotonic() - started) * 1000.0, 2)
                            if self._observation_sink is not None
                            else 0.0
                        )

                    action_decode = self._decoder.decode_cognitive_action(
                        generation=generation,
                        capabilities=capabilities,
                        allowed_memory_references=tuple(memory_reference_ids),
                    )
                    action = action_decode.action
                    if action is None:
                        errors = action_decode.report.validation_errors or (
                            "invalid cognitive action",
                        )
                        add_step(
                            CognitiveStepKind.OBSERVATION,
                            "invalid_cognitive_action",
                            "; ".join(errors),
                            ok=False,
                        )
                        self._emit_action_decoded(
                            task=task,
                            action=None,
                            iteration_index=model_calls,
                            validation_errors=tuple(errors),
                            duration_ms=decode_elapsed_ms(),
                        )
                        if (
                            getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
                            is ReasoningDepth.DELIBERATE
                            and model_calls < active_model_limit
                        ):
                            record_observation(
                                kind="repair",
                                status="invalid_cognitive_action",
                                content=(
                                    f"errors={'; '.join(errors)}; "
                                    f"raw={generation.text[:_MAX_OBSERVATION_CHARS]}; "
                                    "Return one valid CognitiveAction only."
                                ),
                            )
                            current_request = rebuild_request(final_schema=True)
                            continue
                        raise _ReasoningStop(
                            ReasoningStatus.SAFE_NOOP,
                            "cognitive_action_validation_failed",
                        )

                    self._emit_action_decoded(
                        task=task,
                        action=action,
                        iteration_index=model_calls,
                        validation_errors=(),
                        duration_ms=decode_elapsed_ms(),
                    )

                    if isinstance(action, RecallMemory):
                        if (
                            getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
                            is not ReasoningDepth.DELIBERATE
                        ):
                            self._emit_guard(
                                task=task,
                                fired=(
                                    "depth",
                                    ReasoningStatus.SAFE_NOOP,
                                    "recall_memory_not_allowed_in_direct",
                                ),
                                iteration_index=model_calls,
                                model_calls_used=model_calls,
                                active_model_limit=active_model_limit,
                                tool_calls_used=tool_calls,
                                started_at=started_at,
                                deadline_seconds=deadline_seconds,
                                cancelled=(
                                    cancellation is not None and cancellation.is_set()
                                ),
                            )
                            raise _ReasoningStop(
                                ReasoningStatus.SAFE_NOOP,
                                "recall_memory_not_allowed_in_direct",
                            )
                        if reasoning_plan is None and any(
                            observation.kind in {"memory", "revision"}
                            for observation in run_observations
                        ):
                            # One Recall followed by an answer stays plan-free.
                            # A second dependent Recall is the first reliable
                            # signal that this Turn has become multi-step.
                            reasoning_plan = _new_recall_plan()
                            activate_plan_budget()
                            _replace_plan_observation(
                                run_observations,
                                reasoning_plan,
                            )
                        memory_session = getattr(task, "memory_session", None)
                        if memory_session is None:
                            recall_status = "unavailable"
                            recall_reason = "memory_session_unavailable"
                            recall_revision = getattr(task, "memory_recall_revision", 0)
                            recall_bundle = None
                        else:
                            recall_result = memory_session.recall(action.query)
                            recall_status = recall_result.status
                            recall_reason = recall_result.reason
                            recall_revision = recall_result.pinned_revision
                            recall_bundle = recall_result.bundle
                        if recall_bundle is not None:
                            memory_reference_ids.extend(
                                recall_memory_reference_ids(recall_bundle)
                            )
                            memory_reference_ids = list(
                                dict.fromkeys(memory_reference_ids)
                            )
                            recall_content = compile_recall_bundle(
                                recall_bundle,
                                max_tokens=384,
                            ).content
                        else:
                            recall_content = ""
                        observation_content = (
                            f"query={action.query}; reason={action.reason}; "
                            f"result={recall_content or 'no additional memory evidence'}; "
                            f"detail={recall_reason or 'none'}"
                        )
                        if recall_status == "budget_exhausted":
                            observation_content += (
                                "; RecallMemory is exhausted for this Turn; "
                                "do not request RecallMemory again; return a final "
                                "AnswerDraft or ClarificationDraft using only the "
                                "supplied evidence"
                            )
                        add_step(
                            CognitiveStepKind.OBSERVATION,
                            f"memory_{recall_status}",
                            observation_content,
                            operation="memory_recall",
                            ok=recall_status in {"recalled", "duplicate", "skipped"},
                        )
                        record_observation(
                            kind=("revision" if recall_status == "stale" else "memory"),
                            status=recall_status,
                            content=observation_content,
                            source_ids=tuple(
                                f"{kind}:{record_id}"
                                for kind, record_id in recall_memory_reference_ids(
                                    recall_bundle
                                )
                            )
                            if recall_bundle is not None
                            else (),
                            revision=recall_revision,
                        )
                        current_request = rebuild_request(final_schema=True)
                        continue

                    judge_started = (
                        monotonic() if self._observation_sink is not None else 0.0
                    )

                    def judge_elapsed_ms(
                        started: float = judge_started,
                    ) -> float:
                        return (
                            round((monotonic() - started) * 1000.0, 2)
                            if self._observation_sink is not None
                            else 0.0
                        )

                    judge_reason = self._completion_revision_reason(action)
                    judge_sanitized = False
                    if judge_reason is not None:
                        add_step(
                            CognitiveStepKind.VERIFY,
                            "revision_required",
                            judge_reason,
                            ok=False,
                        )
                        if (
                            getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
                            is ReasoningDepth.DELIBERATE
                        ):
                            # The Verifier is a host-owned signal.  It is the
                            # only point at which a correction plan is needed;
                            # accepted first-pass drafts never create one.
                            reasoning_plan = _new_revision_plan()
                            activate_plan_budget()
                            _replace_plan_observation(
                                run_observations,
                                reasoning_plan,
                            )
                        if (
                            getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
                            is ReasoningDepth.DELIBERATE
                            and model_calls < active_model_limit
                        ):
                            record_observation(
                                kind="judge",
                                status="revision_required",
                                content=(
                                    f"{judge_reason}. Revise honestly using only "
                                    "supplied evidence; do not claim external completion."
                                ),
                            )
                            self._emit_judge(
                                task=task,
                                iteration_index=model_calls,
                                action=action,
                                verdict="revision_required",
                                judge_reason=judge_reason,
                                revision_requested=True,
                                external_claim_replaced=False,
                                current_nest_sanitized=False,
                                duration_ms=judge_elapsed_ms(),
                            )
                            current_request = rebuild_request(final_schema=True)
                            continue
                        action = AnswerDraft(
                            type="answer",
                            content=_HONEST_EXTERNAL_BOUNDARY_REPLY,
                        )
                        judge_sanitized = True

                    decode = self._decoder.compile_cognitive_draft(
                        seed=task.seed,
                        action=action,
                        report=action_decode.report,
                    )
                    decode, current_nest_sanitized = self._sanitize_direct_reply(
                        task, decode
                    )
                    verification_summary = self._verification_summary(
                        "CognitiveAction accepted",
                        current_nest_sanitized,
                    )
                    if judge_sanitized:
                        verification_summary += (
                            "; unsupported_external_completion_boundary"
                        )
                    add_step(
                        CognitiveStepKind.VERIFY,
                        "accepted",
                        verification_summary,
                    )
                    self._emit_judge(
                        task=task,
                        iteration_index=model_calls,
                        action=action,
                        verdict="accepted",
                        judge_reason=judge_reason,
                        revision_requested=False,
                        external_claim_replaced=judge_sanitized,
                        current_nest_sanitized=current_nest_sanitized,
                        duration_ms=judge_elapsed_ms(),
                    )
                    return ReasoningRunResult(
                        status=ReasoningStatus.COMPLETED,
                        steps=tuple(steps),
                        model_calls=model_calls,
                        tool_calls=tool_calls,
                        skill_calls=skill_calls,
                        failure_reason=None,
                        decode=decode,
                        plan=reasoning_plan,
                    )

                def repair(raw_text: str, errors: tuple[str, ...]) -> str:
                    nonlocal model_calls, last_generation
                    guard(next_kind=CognitiveStepKind.MODEL, model=True)
                    repair_prompt = (
                        "Repair the following invalid DecisionPlan JSON. Return JSON only.\n"
                        f"Errors: {'; '.join(errors)}\nRaw output:\n{raw_text}"
                    )
                    record_observation(
                        kind="repair",
                        status="invalid_output",
                        content=(
                            f"errors={'; '.join(errors)}; "
                            f"raw={raw_text[:_MAX_OBSERVATION_CHARS]}"
                        ),
                    )
                    repaired_request = rebuild_request(
                        final_schema=True,
                        legacy_prompt=repair_prompt,
                    )
                    remaining_seconds = deadline_seconds - (monotonic() - started_at)
                    repaired = self._observed_generate(
                        repaired_request.model_copy(
                            update={
                                "timeout_seconds": max(
                                    0.001,
                                    remaining_seconds,
                                )
                            }
                        ),
                        iteration_index=model_calls + 1,
                        capabilities=capabilities,
                    )
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
                    allowed_memory_references=tuple(memory_reference_ids),
                )
                decode, reply_was_sanitized = self._sanitize_direct_reply(task, decode)
                plan, preflight_observation = self._preflight_activities(
                    task,
                    decode.plan,
                )
                if preflight_observation is not None:
                    add_step(
                        CognitiveStepKind.OBSERVATION,
                        "activity_preflight",
                        preflight_observation,
                        operation="activity_preflight",
                        ok=False,
                    )
                    activity_prompt = (
                        f"{current_prompt}\n\n"
                        "[Activity Preflight Observation]\n"
                        f"{preflight_observation}\n"
                        "Resolve the missing facts now. Return either a corrected "
                        "DecisionPlan or a scoped clarification message; do not defer "
                        "clarification to the future Activity."
                    )
                    record_observation(
                        kind="activity",
                        status="needs_clarification",
                        content=preflight_observation,
                    )
                    current_request = rebuild_request(
                        final_schema=True,
                        legacy_prompt=activity_prompt,
                    )
                    continue
                if plan is not decode.plan:
                    decode = decode.model_copy(update={"plan": plan})
                if decode.report.fallback_reason is not None:
                    add_step(
                        CognitiveStepKind.VERIFY,
                        "degraded",
                        self._verification_summary(
                            decode.report.fallback_reason,
                            reply_was_sanitized,
                        ),
                    )
                    return ReasoningRunResult(
                        status=ReasoningStatus.SAFE_NOOP,
                        steps=tuple(steps),
                        model_calls=model_calls,
                        tool_calls=tool_calls,
                        skill_calls=skill_calls,
                        failure_reason=decode.report.fallback_reason,
                        decode=decode,
                    )
                add_step(
                    CognitiveStepKind.VERIFY,
                    "accepted",
                    self._verification_summary(
                        "DecisionPlan verified", reply_was_sanitized
                    ),
                )
                return ReasoningRunResult(
                    status=ReasoningStatus.COMPLETED,
                    steps=tuple(steps),
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                    skill_calls=skill_calls,
                    failure_reason=None,
                    decode=decode,
                )
        except _ReasoningStop as stopped:
            self._emit_guard_stop(
                task=task,
                status=stopped.status,
                reason=stopped.reason,
                model_calls=model_calls,
                tool_calls=tool_calls,
                skill_calls=skill_calls,
                step_count=len(steps),
            )
            return self._failure(
                task=task,
                status=stopped.status,
                reason=stopped.reason,
                steps=steps,
                model_calls=model_calls,
                tool_calls=tool_calls,
                skill_calls=skill_calls,
                capabilities=capabilities,
                generation=last_generation,
                reasoning_plan=reasoning_plan,
            )
        except Exception as error:  # noqa: BLE001 - model boundary
            self._emit_run_failed(
                task=task,
                error=error,
                model_calls=model_calls,
                tool_calls=tool_calls,
                skill_calls=skill_calls,
                step_count=len(steps),
            )
            return self._failure(
                task=task,
                status=ReasoningStatus.FAILED,
                reason=f"model_unavailable:{type(error).__name__}",
                steps=steps,
                model_calls=model_calls,
                tool_calls=tool_calls,
                skill_calls=skill_calls,
                capabilities=capabilities,
                generation=last_generation,
                reasoning_plan=reasoning_plan,
            )

    def _observed_generate(
        self,
        request: ModelGenerationRequest,
        *,
        iteration_index: int,
        capabilities: Optional[ModelGenerationCapabilities],
    ) -> ModelGenerationResult:
        """Run one Brain-side model call wrapped by a model_call observation.

        Observation wraps and never alters the call: with no sink wired this
        is a plain ``generate`` with zero observation cost; with a sink, a
        provider exception emits one failed record and then propagates
        unchanged so the Run settles exactly as before.
        """
        sink = self._observation_sink
        if sink is None:
            return self._model_port.generate(request)
        started = monotonic()
        try:
            generation = self._model_port.generate(request)
        except Exception as error:  # noqa: BLE001 - re-raised unchanged below
            self._emit_model_call(
                sink,
                request=request,
                iteration_index=iteration_index,
                duration_ms=(monotonic() - started) * 1000.0,
                capabilities=capabilities,
                generation=None,
                error=error,
            )
            raise
        self._emit_model_call(
            sink,
            request=request,
            iteration_index=iteration_index,
            duration_ms=(monotonic() - started) * 1000.0,
            capabilities=capabilities,
            generation=generation,
            error=None,
        )
        return generation

    def _emit_model_call(
        self,
        sink: BrainObservationSink,
        *,
        request: ModelGenerationRequest,
        iteration_index: int,
        duration_ms: float,
        capabilities: Optional[ModelGenerationCapabilities],
        generation: Optional[ModelGenerationResult],
        error: Optional[Exception],
    ) -> None:
        """Construct and emit one model_call observation; the sink never raises."""
        self._observation_sequence += 1
        if error is not None:
            status = ObservationStatus.failed
            # Provider exception text is untrusted at this boundary, so the
            # sanitized message derives from the exception class name only.
            observation_error: Optional[ObservationError] = ObservationError(
                type=type(error).__name__,
                message=f"model_generate_failed:{type(error).__name__}",
            )
            response_text: Optional[str] = None
            selected_mode: Optional[str] = None
            provider = capabilities.provider if capabilities is not None else None
            model_key = capabilities.model_key if capabilities is not None else None
            prompt_tokens = None
            completion_tokens = None
            provider_latency_ms = None
        else:
            status = ObservationStatus.completed
            observation_error = None
            assert generation is not None  # only failures carry an error
            response_text = generation.text
            selected_mode = generation.selected_mode.value
            provider = generation.provider
            model_key = generation.model_key
            prompt_tokens = generation.prompt_tokens
            completion_tokens = generation.completion_tokens
            provider_latency_ms = generation.latency_ms
        sink.emit(
            BrainObservation[ModelCallObservation](
                boundary="reasoning.agent_loop",
                kind="model_call",
                sequence=self._observation_sequence,
                captured_at=datetime.now(timezone.utc),
                turn_id=str(request.turn_id),
                frame_id=str(request.frame_id),
                cause_event_ids=tuple(str(item) for item in request.cause_event_ids),
                duration_ms=duration_ms,
                status=status,
                error=observation_error,
                payload=ModelCallObservation(
                    iteration_index=iteration_index,
                    system_prompt=request.system_prompt,
                    user_prompt=request.user_prompt,
                    reasoning_mode=request.reasoning_mode,
                    response_mode=request.response_mode.value,
                    response_schema_name=request.response_schema.name,
                    response_schema=request.response_schema.document,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    timeout_seconds=request.timeout_seconds,
                    context_revision=request.context_revision,
                    capability_revision=request.capability_revision,
                    allowed_tools=tuple(str(item) for item in request.allowed_tools),
                    tool_definition_count=len(request.tool_definitions),
                    skill_count=len(request.available_skills),
                    tool_definitions=tuple(request.tool_definitions),
                    available_skills=tuple(request.available_skills),
                    deadline=request.deadline,
                    created_at=request.created_at,
                    response_text=response_text,
                    selected_mode=selected_mode,
                    provider=provider,
                    model_key=model_key,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    provider_latency_ms=provider_latency_ms,
                    duration_ms=duration_ms,
                ),
            )
        )

    def _next_decision_sequence(self) -> int:
        self._decision_sequence += 1
        return self._decision_sequence

    @staticmethod
    def _envelope_causal_ids(task: ReasoningTaskView) -> Tuple[str, ...]:
        return tuple(str(item) for item in task.request.cause_event_ids)

    def _emit_action_decoded(
        self,
        *,
        task: ReasoningTaskView,
        action: Optional[CognitiveAction],
        iteration_index: int,
        validation_errors: Tuple[str, ...],
        duration_ms: float,
    ) -> None:
        """Record one decoded Cognitive Action (§B5-2); unwired = no-op."""
        sink = self._observation_sink
        if sink is None:
            return
        if action is None:
            status = ObservationStatus.failed
            observation_error: Optional[ObservationError] = ObservationError(
                type="cognitive_action_decode_failed",
                message="; ".join(validation_errors)[:_MAX_ERROR_CHARS],
            )
            action_type = None
            query = None
            recall_reason = None
            content = None
            missing_facts: Tuple[str, ...] = ()
            noop_reason = None
            memory_use_count = 0
        else:
            status = ObservationStatus.completed
            observation_error = None
            action_type = type(action).__name__
            query = None
            recall_reason = None
            content = None
            missing_facts = ()
            noop_reason = None
            if isinstance(action, RecallMemory):
                query = action.query
                recall_reason = action.reason
            elif isinstance(action, NoOpDraft):
                noop_reason = action.reason
            else:
                content = action.content
                if isinstance(action, ClarificationDraft):
                    missing_facts = tuple(action.missing_facts)
            memory_use_count = len(getattr(action, "memory_uses", ()) or ())
        sink.emit(
            BrainObservation[AgentLoopActionObservation](
                boundary="reasoning.agent_loop",
                kind="action_decoded",
                sequence=self._next_decision_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id=str(task.request.turn_id),
                frame_id=str(task.request.frame_id),
                cause_event_ids=self._envelope_causal_ids(task),
                duration_ms=duration_ms,
                status=status,
                error=observation_error,
                payload=AgentLoopActionObservation(
                    iteration_index=iteration_index,
                    action_type=action_type,
                    query=query,
                    recall_reason=recall_reason,
                    content=content,
                    missing_facts=missing_facts,
                    noop_reason=noop_reason,
                    memory_use_count=memory_use_count,
                    validation_errors=validation_errors,
                ),
            )
        )

    def _emit_observation_recorded(
        self,
        *,
        task: ReasoningTaskView,
        observation: CurrentRunObservation,
        iteration_index: int,
        duration_ms: float,
    ) -> None:
        """Record one Run observation append (§B5-3); unwired = no-op."""
        sink = self._observation_sink
        if sink is None:
            return
        sink.emit(
            BrainObservation[AgentLoopObservationRecorded](
                boundary="reasoning.agent_loop",
                kind="observation",
                sequence=self._next_decision_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id=str(task.request.turn_id),
                frame_id=str(task.request.frame_id),
                cause_event_ids=self._envelope_causal_ids(task),
                duration_ms=duration_ms,
                status=ObservationStatus.completed,
                payload=AgentLoopObservationRecorded(
                    iteration_index=iteration_index,
                    observation_kind=observation.kind,
                    observation_status=observation.status,
                    content=observation.content,
                    source_ids=observation.source_ids,
                    revision=observation.revision,
                ),
            )
        )

    def _emit_guard(
        self,
        *,
        task: ReasoningTaskView,
        fired: Optional[Tuple[str, ReasoningStatus, str]],
        iteration_index: int,
        model_calls_used: int,
        active_model_limit: int,
        tool_calls_used: int,
        started_at: float,
        deadline_seconds: Optional[float],
        cancelled: bool,
    ) -> None:
        """Record one Guard verdict (§B5-4); unwired = no-op."""
        sink = self._observation_sink
        if sink is None:
            return
        guard_name: Literal[
            "none",
            "cancellation",
            "deadline",
            "model_budget",
            "tool_budget",
            "steps",
            "depth",
        ]
        if fired is None:
            guard_name = "none"
            may_continue = True
            stop_reason = None
        else:
            guard_name = cast(
                Literal[
                    "none",
                    "cancellation",
                    "deadline",
                    "model_budget",
                    "tool_budget",
                    "steps",
                    "depth",
                ],
                fired[0],
            )
            may_continue = False
            stop_reason = fired[2]
        deadline_remaining_ms: Optional[float] = None
        if deadline_seconds is not None:
            deadline_remaining_ms = max(
                0.0, (deadline_seconds - (monotonic() - started_at)) * 1000.0
            )
        depth = getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
        sink.emit(
            BrainObservation[AgentLoopGuardObservation](
                boundary="reasoning.agent_loop",
                kind="guard",
                sequence=self._next_decision_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id=str(task.request.turn_id),
                frame_id=str(task.request.frame_id),
                cause_event_ids=self._envelope_causal_ids(task),
                duration_ms=0.0,
                status=ObservationStatus.completed,
                payload=AgentLoopGuardObservation(
                    iteration_index=iteration_index,
                    guard=guard_name,
                    may_continue=may_continue,
                    outcome="stopped" if fired is not None else "continued",
                    depth=depth.value,
                    model_calls_used=model_calls_used,
                    max_model_calls=active_model_limit,
                    model_calls_remaining=max(0, active_model_limit - model_calls_used),
                    tool_calls_used=tool_calls_used,
                    max_tool_calls=self._budget.max_tool_calls,
                    deadline_remaining_ms=deadline_remaining_ms,
                    cancelled=cancelled,
                    stop_reason=stop_reason,
                ),
            )
        )

    def _emit_guard_stop(
        self,
        *,
        task: ReasoningTaskView,
        status: ReasoningStatus,
        reason: str,
        model_calls: int,
        tool_calls: int,
        skill_calls: int,
        step_count: int,
    ) -> None:
        """Record one guard-driven terminal stop (§B5-4); unwired = no-op."""
        sink = self._observation_sink
        if sink is None:
            return
        depth = getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
        sink.emit(
            BrainObservation[AgentLoopGuardStopObservation](
                boundary="reasoning.agent_loop",
                kind="guard_stop",
                sequence=self._next_decision_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id=str(task.request.turn_id),
                frame_id=str(task.request.frame_id),
                cause_event_ids=self._envelope_causal_ids(task),
                duration_ms=0.0,
                status=ObservationStatus.completed,
                payload=AgentLoopGuardStopObservation(
                    status=status.value,
                    reason=reason,
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                    skill_calls=skill_calls,
                    step_count=step_count,
                    depth=depth.value,
                ),
            )
        )

    def _emit_run_failed(
        self,
        *,
        task: ReasoningTaskView,
        error: Exception,
        model_calls: int,
        tool_calls: int,
        skill_calls: int,
        step_count: int,
    ) -> None:
        """Record the non-guard failure closure of one Run (§B5 G-M10).

        Emitted exactly once by the generic ``except Exception`` boundary
        before the safe-failure result is returned unchanged.  The
        exception class name is the only untrusted-derived content; the
        exception text never enters the observation.  Envelope ``status``
        is ``failed`` with a sanitized ``ObservationError``.
        """
        sink = self._observation_sink
        if sink is None:
            return
        depth = getattr(task, "reasoning_depth", ReasoningDepth.DIRECT)
        sink.emit(
            BrainObservation[AgentLoopRunFailedObservation](
                boundary="reasoning.agent_loop",
                kind="run_failed",
                sequence=self._next_decision_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id=str(task.request.turn_id),
                frame_id=str(task.request.frame_id),
                cause_event_ids=self._envelope_causal_ids(task),
                duration_ms=0.0,
                status=ObservationStatus.failed,
                error=ObservationError(
                    type=type(error).__name__,
                    message=f"agent_loop_failed:{type(error).__name__}",
                ),
                payload=AgentLoopRunFailedObservation(
                    turn_id=str(task.request.turn_id),
                    frame_id=str(task.request.frame_id),
                    error_type=type(error).__name__,
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                    skill_calls=skill_calls,
                    step_count=step_count,
                    depth=depth.value,
                ),
            )
        )

    def _emit_judge(
        self,
        *,
        task: ReasoningTaskView,
        iteration_index: int,
        action: CognitiveAction,
        verdict: Literal["accepted", "revision_required"],
        judge_reason: Optional[str],
        revision_requested: bool,
        external_claim_replaced: bool,
        current_nest_sanitized: bool,
        duration_ms: float,
    ) -> None:
        """Record one Completion Judge verdict (§B6); unwired = no-op."""
        sink = self._observation_sink
        if sink is None:
            return
        sink.emit(
            BrainObservation[AgentLoopJudgeObservation](
                boundary="reasoning.completion",
                kind="judge",
                sequence=self._next_decision_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id=str(task.request.turn_id),
                frame_id=str(task.request.frame_id),
                cause_event_ids=self._envelope_causal_ids(task),
                duration_ms=duration_ms,
                status=ObservationStatus.completed,
                payload=AgentLoopJudgeObservation(
                    iteration_index=iteration_index,
                    action_type=type(action).__name__,
                    verdict=verdict,
                    content=getattr(action, "content", ""),
                    judge_reason=judge_reason,
                    revision_requested=revision_requested,
                    external_claim_replaced=external_claim_replaced,
                    current_nest_sanitized=current_nest_sanitized,
                    memory_use_count=len(getattr(action, "memory_uses", ()) or ()),
                ),
            )
        )

    def _request(
        self,
        base: ModelGenerationRequest,
        user_prompt: str,
        *,
        final_schema: bool = False,
        capabilities: ModelGenerationCapabilities | None = None,
        allow_deliberate_tools: bool = False,
    ) -> ModelGenerationRequest:
        del final_schema
        direct_reply = self._is_fast_owner_reply(base)
        response_schema = base.response_schema
        native_tools = (
            allow_deliberate_tools
            and capabilities is not None
            and capabilities.supports_tool_calling
        )
        allowed_tools = (
            base.allowed_tools
            if (not direct_reply and self._tool_port is not None and native_tools)
            else ()
        )
        available_skills = (
            base.available_skills if not direct_reply and native_tools else ()
        )
        return base.model_copy(
            update={
                "system_prompt": _with_brain_owned_schema_protocol(
                    base.system_prompt,
                    response_schema,
                    capabilities,
                ),
                "user_prompt": user_prompt,
                "response_schema": response_schema,
                "allowed_tools": allowed_tools,
                "available_skills": available_skills,
            }
        )

    @staticmethod
    def _is_fast_owner_reply(request: ModelGenerationRequest) -> bool:
        return request.response_mode is ModelResponseMode.DIRECT_REPLY

    @staticmethod
    def _sanitize_direct_reply(
        task: ReasoningTaskView,
        decode: DecisionDecodeResult,
    ) -> tuple[DecisionDecodeResult, bool]:
        if task.request.response_mode is not ModelResponseMode.DIRECT_REPLY:
            return decode, False
        context = getattr(task, "reply_safety_context", None)
        if context is None:
            return decode, False
        changed = False
        intents: list[DecisionIntent] = []
        for intent in decode.plan.intents:
            if not isinstance(intent, MessageIntent):
                intents.append(intent)
                continue
            content = sanitize_direct_owner_reply(intent.content, context)
            changed = changed or content != intent.content
            intents.append(
                intent.model_copy(update={"content": content})
                if content != intent.content
                else intent
            )
        if not changed:
            return decode, False
        plan = decode.plan.model_copy(update={"intents": tuple(intents)})
        return decode.model_copy(update={"plan": plan}), True

    @staticmethod
    def _verification_summary(reason: str, reply_was_sanitized: bool) -> str:
        if not reply_was_sanitized:
            return reason
        return f"{reason}; direct_reply_current_nest_boundary"

    @staticmethod
    def _completion_revision_reason(action: CognitiveAction) -> str | None:
        """Reject unsupported external-completion claims before decision binding."""
        if not isinstance(action, (AnswerDraft, ClarificationDraft)):
            return None
        if _UNSUPPORTED_EXTERNAL_COMPLETION.search(action.content) is not None:
            return "unsupported_external_completion_claim"
        return None

    @staticmethod
    def _tool_request_from_call(task: ReasoningTaskView, call: ToolCall) -> ToolRequest:
        arguments = dict(call.arguments)
        if call.tool_key == "web_search":
            return ToolRequest(
                tool_key=call.tool_key,
                operation="search",
                query=str(arguments.get("query") or ""),
                max_results=_json_int(arguments.get("max_results", 3), 3),
            )
        if call.tool_key != "local_file":
            raise ValueError(f"unknown semantic Tool: {call.tool_key}")
        return ToolRequest(
            scope_id=getattr(task, "tool_scope_id", None),
            tool_key="local_file",
            operation=_tool_operation(arguments.get("operation"), "read"),
            resource_id=str(arguments.get("resource_id") or ""),
        )

    @staticmethod
    def _load_skill(
        request: ModelGenerationRequest,
        task: ReasoningTaskView,
        call: SkillLoadCall,
    ):
        """Load one advertised Skill through the injected read-only catalog."""
        advertised = {item.name for item in request.available_skills}
        if call.skill_name not in advertised:
            return None
        catalog = getattr(task, "skill_catalog", None)
        if catalog is None:
            return None
        return catalog.load(call.skill_name)

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

    @staticmethod
    def _skill_observation_prompt(
        original_prompt: str,
        skill_name: str,
        instructions: str,
    ) -> str:
        """Make a loaded procedural Skill visible on the next model request."""
        return (
            f"{original_prompt}\n\n"
            f"[Loaded Skill: {skill_name}]\n"
            f"{instructions[:_MAX_OBSERVATION_CHARS]}\n"
            "Follow these instructions and return a DecisionPlan JSON object only."
        )

    def _preflight_activities(
        self,
        task: ReasoningTaskView,
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
            result = self._activity_preflight.preflight(
                request.draft,
                turn_id=str(task.request.turn_id),
                frame_id=str(task.request.frame_id),
            )
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
        skill_calls: int,
        capabilities: Optional[ModelGenerationCapabilities],
        generation: Optional[ModelGenerationResult],
        reasoning_plan: Optional[ReasoningPlan],
    ) -> ReasoningRunResult:
        decode = self._safe_noop(
            task,
            reason,
            capabilities=capabilities,
            generation=generation,
        )
        if self._budget.max_steps is None or len(steps) < self._budget.max_steps:
            steps.append(
                CognitiveStep(
                    ordinal=len(steps) + 1,
                    kind=CognitiveStepKind.VERIFY,
                    status=(
                        "fallback"
                        if decode.plan.intents[0].type == "message"
                        else "safe_noop"
                    ),
                    summary=reason,
                )
            )
        return ReasoningRunResult(
            status=status,
            steps=tuple(steps),
            model_calls=model_calls,
            tool_calls=tool_calls,
            skill_calls=skill_calls,
            failure_reason=reason,
            decode=decode,
            plan=reasoning_plan,
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
        intent: DecisionIntent
        if seed.reply_channel_id and seed.reply_conversation_id:
            intent = MessageIntent(
                type="message",
                intent_id=IntentId(f"reasoning-fallback-intent-{seed.turn_id}"),
                cause_event_ids=seed.cause_event_ids,
                dependency_ids=(),
                deadline=seed.deadline,
                cancel_policy=CancelPolicy.ALWAYS,
                channel_id=seed.reply_channel_id,
                conversation_id=seed.reply_conversation_id,
                content=TRUSTED_OWNER_FAILURE_REPLY,
            )
        else:
            intent = NoOpIntent(
                type="noop",
                intent_id=IntentId(f"reasoning-noop-intent-{seed.turn_id}"),
                cause_event_ids=seed.cause_event_ids,
                dependency_ids=(),
                deadline=seed.deadline,
                cancel_policy=CancelPolicy.IF_NOT_STARTED,
                reason=reason,
            )
        plan = DecisionPlan(
            plan_id=PlanId(
                f"reasoning-fallback-{seed.turn_id}"
                if seed.reply_channel_id and seed.reply_conversation_id
                else f"reasoning-noop-{seed.turn_id}"
            ),
            turn_id=seed.turn_id,
            frame_id=seed.frame_id,
            context_revision=seed.context_revision,
            capability_revision=seed.capability_revision,
            created_at=seed.created_at,
            deadline=seed.deadline,
            cause_event_ids=seed.cause_event_ids,
            intents=(intent,),
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
    "CurrentRunObservation",
    "ReasoningBudget",
    "ReasoningDepth",
    "ReasoningPlan",
    "ReasoningRun",
    "ReasoningRunResult",
    "ReasoningStatus",
)
