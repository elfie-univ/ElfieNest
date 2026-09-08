"""Named frozen payloads for the Reasoning agent-loop boundaries.

``ModelCallObservation`` is the §B5 Agent Loop ``model_call`` payload emitted
at the Brain-side ``ModelPort.generate`` boundary, covering both the primary
generation and the repair/revision generation of one Run.  The decision
payloads added below cover the remaining §B5 internal decisions — decoded
Cognitive Actions, recorded Run observations, Guard verdicts and guard stops —
and the §B6 Completion Judge verdict on one final draft.  Every field is a raw
value the emitting code already holds at the emit point (P1 raw capture, no
inferred data).

The Brain does NOT redact: raw prompt and response text flows into the
payload, and redaction is the sink side's responsibility.  The one exception
is ``ObservationError.message`` on failed calls, which the emit site
sanitizes to the exception class name because provider exception text is
untrusted at this boundary.

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import Field

from elfie.message_types import FrozenContractModel, UTCDateTime


class ModelCallObservation(FrozenContractModel):
    """One Brain-side model call at the agent-loop boundary (§B5-1).

    Request-side fields mirror ``ModelGenerationRequest``.  Response-side
    fields are ``None`` exactly when the model call failed.  ``provider`` and
    ``model_key`` carry the identity the Brain actually knows here: the served
    model from ``ModelGenerationResult`` on success, the selected capability
    identity on failure.  ``duration_ms`` is the boundary-measured wall-clock
    duration of the ``generate`` call; ``provider_latency_ms`` is the
    provider-reported latency when the result supplies one.
    ``allowed_tools``/``tool_definition_count``/``skill_count`` mirror the
    frozen capability sets the request carried, and ``deadline``/
    ``created_at`` are the Turn-level bounds copied verbatim from the
    request the Brain actually sent.
    """

    iteration_index: int = Field(ge=1)
    # Request side (what the Brain sent; raw text, the sink side redacts).
    system_prompt: str
    user_prompt: str
    reasoning_mode: str
    response_mode: str
    response_schema_name: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1)
    context_revision: int = Field(ge=0)
    capability_revision: int = Field(ge=0)
    allowed_tools: Tuple[str, ...] = ()
    tool_definition_count: int = Field(default=0, ge=0)
    skill_count: int = Field(default=0, ge=0)
    deadline: Optional[UTCDateTime] = None
    created_at: Optional[UTCDateTime] = None
    # Response side (None when the model call failed).
    response_text: Optional[str] = None
    selected_mode: Optional[str] = None
    provider: Optional[str] = None
    model_key: Optional[str] = None
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    provider_latency_ms: Optional[float] = Field(default=None, ge=0.0)
    # Boundary-measured wall-clock duration of the generate call.
    duration_ms: float = Field(ge=0.0)


class AgentLoopActionObservation(FrozenContractModel):
    """One decoded Cognitive Action draft (§B5-2).

    Field groups are populated exactly for the decoded action kind:
    ``query``/``recall_reason`` for RecallMemory, ``content`` for
    Answer/Clarification drafts, ``missing_facts`` for ClarificationDraft,
    ``noop_reason`` for NoOpDraft.  ``action_type`` is ``None`` only when
    the decode failed, in which case ``validation_errors`` carries the
    decoder's raw error list.
    """

    iteration_index: int = Field(ge=1)
    action_type: Optional[str] = None
    query: Optional[str] = None
    recall_reason: Optional[str] = None
    content: Optional[str] = None
    missing_facts: Tuple[str, ...] = ()
    noop_reason: Optional[str] = None
    memory_use_count: int = Field(default=0, ge=0)
    validation_errors: Tuple[str, ...] = ()


class AgentLoopObservationRecorded(FrozenContractModel):
    """One Run observation recorded for the next Context Engine pass (§B5-3).

    Mirrors the ``CurrentRunObservation`` the worker just appended; the
    short-plan state rows replaced by ``_replace_plan_observation`` are not
    record points (they are plan state, rewritten every time).
    """

    iteration_index: int = Field(ge=1)
    observation_kind: str
    observation_status: str
    content: str
    source_ids: Tuple[str, ...] = ()
    revision: Optional[int] = Field(default=None, ge=0)


class AgentLoopGuardObservation(FrozenContractModel):
    """One Guard verdict at the loop admission boundary (§B5-4).

    ``guard`` names the single check that produced the verdict — the first
    failed check when stopping, ``"none"`` when the Run may continue.
    ``max_model_calls`` is the active limit, which a host-owned plan may
    have expanded from the frozen budget value.  The envelope ``status``
    stays ``completed`` under the unified status rule: the guard ran and
    produced its verdict; the stop polarity is carried here by
    ``may_continue``/``outcome``/``stop_reason``.
    """

    iteration_index: int = Field(ge=1)
    guard: Literal[
        "none",
        "cancellation",
        "deadline",
        "model_budget",
        "tool_budget",
        "steps",
        "depth",
    ]
    may_continue: bool
    outcome: Literal["continued", "stopped"]
    depth: Literal["direct", "deliberate"]
    model_calls_used: int = Field(ge=0)
    max_model_calls: int = Field(ge=1)
    model_calls_remaining: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    max_tool_calls: int = Field(ge=0)
    deadline_remaining_ms: Optional[float] = Field(default=None, ge=0.0)
    cancelled: bool
    stop_reason: Optional[str] = None


class AgentLoopGuardStopObservation(FrozenContractModel):
    """One guard-driven terminal stop of the Run (§B5-4 stop sample).

    Emitted once per ``_ReasoningStop`` in the Run's failure closure with
    the same reason the Run records; non-guard failures (provider
    exceptions) settle through the failed ``model_call`` record instead,
    and any other non-stop exception through ``AgentLoopRunFailedObservation``.
    The envelope ``status`` stays ``completed`` under the unified status
    rule: the guard ran to its normal end; ``status``/``reason`` here
    carry the stop polarity.
    """

    status: str
    reason: str
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    skill_calls: int = Field(ge=0)
    step_count: int = Field(ge=0)
    depth: Literal["direct", "deliberate"]


class AgentLoopRunFailedObservation(FrozenContractModel):
    """One non-guard agent-loop failure closure (§B5 failure visibility).

    Emitted exactly once by the Run's generic ``except Exception``
    boundary before the safe-failure result is built, so a Run that dies
    outside the guard/model-call records (decoder plumbing, context
    rebuild, recall session) still leaves one terminal record on the
    agent-loop boundary.  ``error_type`` is the sanitized exception class
    name; the exception text is never transported.
    """

    turn_id: str
    frame_id: str
    error_type: str
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    skill_calls: int = Field(ge=0)
    step_count: int = Field(ge=0)
    depth: Literal["direct", "deliberate"]


class AgentLoopJudgeObservation(FrozenContractModel):
    """One Completion Judge verdict on a draft (§B6).

    ``content`` is the draft text the verdict applies to — the model's
    original draft for ``revision_required``, the final (possibly
    replaced/sanitized) draft for ``accepted``.  ``judge_reason`` is the
    host check behind the verdict: the check that demands revision, the
    check that triggered the trusted replacement when
    ``external_claim_replaced`` is set, and ``None`` when the final draft
    passed cleanly.  ``current_nest_sanitized`` marks the direct-reply
    boundary rewrite.
    """

    iteration_index: int = Field(ge=1)
    action_type: str
    verdict: Literal["accepted", "revision_required"]
    content: str
    judge_reason: Optional[str] = None
    revision_requested: bool = False
    external_claim_replaced: bool = False
    current_nest_sanitized: bool = False
    memory_use_count: int = Field(default=0, ge=0)


__all__ = (
    "AgentLoopActionObservation",
    "AgentLoopGuardObservation",
    "AgentLoopGuardStopObservation",
    "AgentLoopJudgeObservation",
    "AgentLoopObservationRecorded",
    "AgentLoopRunFailedObservation",
    "ModelCallObservation",
)
