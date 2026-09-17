"""Project the production Brain Turn into a compact, provenance-preserving trace.

This module is deliberately a read-only projection.  The Brain remains the
owner of execution facts; the Lab only groups the records that already exist
on a ``TurnRecord`` plus the raw ``BrainObservation`` envelopes the session
captured during the turn, so one Turn can be inspected as one causal chain.
Memory and context views are rebuilt exclusively from those typed events —
no prompt text is ever parsed back into structure here.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from elfie.brain.observation import BrainObservation

_MEMORY_BRIDGE_BOUNDARY = "reasoning.memory_bridge"
_CONTEXT_ENGINE_BOUNDARY = "reasoning.context_engine"
_MEMORY_ENCODE_BOUNDARY = "memory.encode"
_AGENT_LOOP_BOUNDARY = "reasoning.agent_loop"
_WORKSPACE_BOUNDARY = "workspace"
_CONTEXT_WORKSPACE_BOUNDARY = "reasoning.context_workspace"
_RUN_CONTROLLER_BOUNDARY = "reasoning.run_controller"
_SELFHOOD_BOUNDARY = "selfhood"
_EMOTION_BOUNDARY = "emotion"
_ENERGY_BOUNDARY = "energy"
_DECISION_BOUNDARY = "decision_boundary"
# Agent-loop envelope kinds whose payloads carry a stable ``iteration_index``;
# ``guard_stop`` / ``run_failed`` are run-level terminal records without one.
_AGENT_LOOP_ITERATION_KINDS = (
    "model_call",
    "action_decoded",
    "observation",
    "guard",
    "judge",
)

# ---------------------------------------------------------------------------
# Per-stage duration membership
#
# Every chain node reports ``duration_ms`` as the SUM of the real measured
# ``duration_ms`` values the Brain already recorded on the observation
# envelopes belonging to that stage.  Membership is derived from the data
# each stage function renders (emit order alone would misattribute events
# that a later stage renders), not re-measured or inferred:
#
#   Stage (id)             boundary                      kinds
#   ---------------------  ----------------------------  -------------------
#   1 event_admission      workspace                     frame_claim
#   2 context_workspace    reasoning.context_workspace   conversation_appended
#   3 setup                reasoning.memory_bridge       turn_opened,
#                                                        recall_started,
#                                                        recall_result
#   3 setup                memory.encode                 use_proposal_recorded
#                                                        (rendered as the
#                                                        memory view's
#                                                        "selected" block,
#                                                        surfaced in setup's
#                                                        baseline_memory)
#   4 reasoning_run        reasoning.run_controller      mode_selected,
#                                                        budget_frozen
#   4 reasoning_run        reasoning.context_engine      context_trimmed,
#                                                        compiled_context
#   4 reasoning_run        reasoning.agent_loop          model_call,
#                                                        action_decoded,
#                                                        observation, guard,
#                                                        guard_stop, run_failed
#   4 reasoning_run        reasoning.completion          judge
#   4 reasoning_run        selfhood                      projection_snapshot
#   4 reasoning_run        orientation                   orientation_snapshot
#   4 reasoning_run        emotion                       appraisal_input,
#                                                        emotion_candidate
#   4 reasoning_run        motivation                    drive_evaluated
#   4 reasoning_run        energy                        budget_reserve
#   5 turn_decision        decision_boundary             decision_routed
#   6 governance_delivery  activity                      preflight_verdict
#   7 settlement           energy                        budget_settled,
#                                                        budget_released
#   7 settlement           memory.encode                 encode_candidate,
#                                                        encode_commit,
#                                                        reinforcement_applied
#
# ``memory.encode`` genuinely spans two stages and is split by kind: the
# use-proposal events render in the memory view (setup's baseline memory),
# while encode/commit/reinforcement records are settlement-time persistence
# facts.  A stage with no member events reports ``duration_ms: None``; a
# member event without a measured duration contributes zero.  The whole-turn
# ``duration_ms`` stays only on the trace root and the settlement node's
# ``output.duration_ms``; per-stage values never overwrite it.
# ---------------------------------------------------------------------------
_STAGE_EVENT_MEMBERS: Dict[str, Tuple[Tuple[str, Tuple[str, ...]], ...]] = {
    "event_admission": (("workspace", ("frame_claim",)),),
    "context_workspace": (("reasoning.context_workspace", ("conversation_appended",)),),
    "setup": (
        (
            _MEMORY_BRIDGE_BOUNDARY,
            ("turn_opened", "recall_started", "recall_result"),
        ),
        (_MEMORY_ENCODE_BOUNDARY, ("use_proposal_recorded",)),
    ),
    "reasoning_run": (
        ("reasoning.run_controller", ("mode_selected", "budget_frozen")),
        (_CONTEXT_ENGINE_BOUNDARY, ("context_trimmed", "compiled_context")),
        (
            _AGENT_LOOP_BOUNDARY,
            (
                "model_call",
                "action_decoded",
                "observation",
                "guard",
                "guard_stop",
                "run_failed",
            ),
        ),
        ("reasoning.completion", ("judge",)),
        ("selfhood", ("projection_snapshot",)),
        ("orientation", ("orientation_snapshot",)),
        ("emotion", ("appraisal_input", "emotion_candidate")),
        ("motivation", ("drive_evaluated",)),
        ("energy", ("budget_reserve",)),
    ),
    "turn_decision": (("decision_boundary", ("decision_routed",)),),
    "governance_delivery": (("activity", ("preflight_verdict",)),),
    "settlement": (
        ("energy", ("budget_settled", "budget_released")),
        (
            _MEMORY_ENCODE_BOUNDARY,
            ("encode_candidate", "encode_commit", "reinforcement_applied"),
        ),
    ),
}


def _stage_duration(
    observations: Sequence[BrainObservation],
    boundaries_and_kinds: Sequence[Tuple[str, Tuple[str, ...]]],
    *,
    frame_id: Any = None,
) -> Optional[float]:
    """Sum the measured ``duration_ms`` of one stage's member envelopes.

    Read-only over the envelopes the Brain already recorded: no duration
    is re-measured or inferred.  A member event without a measured
    duration contributes zero, and a stage with no member events at all
    reports ``None`` so the frontend renders the honest "未记录".  When the
    turn frame is known, a different frame is never allowed to contribute a
    duration to this turn's header.
    """
    member_durations = [
        event.duration_ms
        for event in observations
        if (not frame_id or str(event.frame_id) == str(frame_id))
        if any(
            event.boundary == boundary and event.kind in kinds
            for boundary, kinds in boundaries_and_kinds
        )
    ]
    if not member_durations:
        return None
    return float(sum(value for value in member_durations if value is not None))


def _event_duration_sum(events: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """Sum measured durations for one projected sub-step.

    The envelope owns timing.  A present event with no measured duration is
    still a real event and therefore reports ``0.0``; no elapsed time is
    inferred from neighboring records.
    """
    if not events:
        return None
    return float(
        sum(
            value
            for value in (event.get("duration_ms") for event in events)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
    )


def _scoped_events(
    observations: Sequence[BrainObservation],
    *,
    boundary: str,
    kinds: Tuple[str, ...],
    frame_id: Any,
) -> List[BrainObservation]:
    """Collect one boundary's envelopes, keeping the turn's frame when known.

    Mirrors the existing helpers' scoping rule: when the turn frame is
    known and at least one envelope matches it, envelopes of other frames
    are dropped so a concurrent autonomous turn cannot leak into this view;
    otherwise the unscoped emit order is kept.
    """
    events = [
        event
        for event in observations
        if event.boundary == boundary and event.kind in kinds
    ]
    if frame_id:
        scoped = [event for event in events if str(event.frame_id) == str(frame_id)]
        if scoped:
            events = scoped
    return events


def _turn_context_trims(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> List[BrainObservation]:
    """Dump the turn's ``context_trimmed`` envelopes in emit order.

    Uses the same frame scoping as :func:`_turn_compiles` so the positional
    trim↔compile pairing below stays aligned with the compiles list.
    """
    events = [
        event
        for event in observations
        if event.boundary == _CONTEXT_ENGINE_BOUNDARY
        and event.kind == "context_trimmed"
    ]
    if frame_id:
        events = [event for event in events if str(event.frame_id) == str(frame_id)]
    return events


def _admission_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the ``workspace``/``frame_claim`` payload (Gap 1).

    Only raw payload values: the salience tuples stay per-event rows and a
    missing claim reports ``None`` — never invented.
    """
    events = _scoped_events(
        observations,
        boundary=_WORKSPACE_BOUNDARY,
        kinds=("frame_claim",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[0].payload
    return {
        "admitted": payload.admitted,
        "trigger_reason": payload.trigger_reason,
        "cutoff_seq": payload.cutoff_seq,
        "event_count": payload.event_count,
        "max_event_salience": payload.max_event_salience,
        "saliences": [
            {"event_id": item.event_id, "salience": item.salience}
            for item in payload.event_saliences
        ],
        "detail": payload.detail,
    }


def _appended_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the ``conversation_appended`` payload (Gap 2)."""
    events = _scoped_events(
        observations,
        boundary=_CONTEXT_WORKSPACE_BOUNDARY,
        kinds=("conversation_appended",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[0].payload
    return {
        "message_count": payload.message_count,
        "active_topic_message_count": payload.active_topic_message_count,
        "channel_id": payload.channel_id,
        "conversation_id": payload.conversation_id,
        # Keep the causal input identity available to the read-side
        # projection so the current message can stay in Event Workspace
        # instead of being duplicated in Context Workspace.
        "input_event_ids": list(payload.input_event_ids),
        "summaries": [
            {
                "summary_id": item.summary_id,
                "version": item.version,
                "unresolved_count": item.unresolved_count,
            }
            for item in payload.summaries
        ],
    }


def _context_current_event_ids(
    appended: Optional[Mapping[str, Any]],
    decision: Mapping[str, Any],
) -> List[str]:
    """Identify this turn's input and derived reply event identities.

    The Context Workspace owns reply event ids as ``elfie-reply:<intent_id>``
    when a message intent is prepared.  Reusing that existing deterministic
    identity lets the UI hide the whole current interaction from the history
    disclosure while keeping the checkpoint itself complete.
    """
    ids = [
        str(item)
        for item in _sequence(
            appended.get("input_event_ids") if appended is not None else ()
        )
    ]
    for value in _sequence(decision.get("message_intents")):
        intent_id = _mapping(value).get("intent_id")
        if intent_id:
            ids.append(f"elfie-reply:{intent_id}")
    return ids


def _mode_selection_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the ``mode_selected`` payload fields setup renders (Gap 3)."""
    events = _scoped_events(
        observations,
        boundary=_RUN_CONTROLLER_BOUNDARY,
        kinds=("mode_selected",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[0].payload
    return {
        "depth": payload.depth,
        "depth_basis": payload.depth_basis,
        "reasoning_mode": payload.reasoning_mode,
        "response_mode": payload.response_mode,
        "requires_model": payload.requires_model,
        "structured_owner_reply": payload.structured_owner_reply,
        "fast_owner_reply": payload.fast_owner_reply,
        "effective_tools": list(payload.effective_tools),
        "skill_count": payload.skill_count,
    }


def _budget_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the ``budget_frozen`` payload into setup's budget block (Gap 3)."""
    events = _scoped_events(
        observations,
        boundary=_RUN_CONTROLLER_BOUNDARY,
        kinds=("budget_frozen",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[0].payload
    return {
        "max_steps": payload.max_steps,
        "max_model_calls": payload.max_model_calls,
        "max_planned_model_calls": payload.max_planned_model_calls,
        "max_tool_calls": payload.max_tool_calls,
        "deadline_seconds": payload.deadline_seconds,
        "hard_deadline_seconds": payload.hard_deadline_seconds,
        "absolute_deadline": _iso_utc(payload.absolute_deadline),
        "max_context_tokens": payload.max_context_tokens,
        "cognitive_mode": payload.cognitive_mode,
        "long_reasoning_allowed": payload.long_reasoning_allowed,
    }


def _selfhood_projection_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the ``projection_snapshot`` payload the setup view expands.

    The confirmed field list renders the selfhood projection text in the
    setup card's expanded section; the projection is the raw payload the
    ``selfhood`` boundary already recorded.
    """
    events = _scoped_events(
        observations,
        boundary=_SELFHOOD_BOUNDARY,
        kinds=("projection_snapshot",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[-1].payload
    return {
        "revision": payload.revision,
        "projected_at": _iso_utc(payload.projected_at),
        "identity_core_text": payload.identity_core_text,
        "adaptive_self_text": payload.adaptive_self_text,
    }


def _context_frozen_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the exact owner snapshots sealed into ``BrainContext``.

    Setup must read this event rather than ``state_before``: the latter is a
    Lab fixture used for injection/diff and can be older than the snapshots
    actually assembled for the reasoning request.
    """
    events = _scoped_events(
        observations,
        boundary=_RUN_CONTROLLER_BOUNDARY,
        kinds=("context_frozen",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[-1].payload
    return {
        "context_revision": payload.context_revision,
        "constitution_version": payload.constitution_version,
        "context_captured_at": _iso_utc(payload.context_captured_at),
        "emotion": payload.emotion.model_dump(mode="json"),
        "homeostasis": payload.homeostasis.model_dump(mode="json"),
        "motivation": payload.motivation.model_dump(mode="json"),
        "orientation": payload.orientation.model_dump(mode="json"),
        "selfhood": payload.selfhood.model_dump(mode="json"),
    }


def _trim_view(payload: Any) -> Dict[str, Any]:
    """Project one ``context_trimmed`` payload (Gap 4)."""
    return {
        "max_tokens": payload.max_tokens,
        "reserved": payload.reserved,
        "memory_budget": payload.memory_budget,
        "content_budget": payload.content_budget,
        "event_budget": payload.event_budget,
        "observation_budget": payload.observation_budget,
        "truncated": payload.truncated,
        "memory_truncated": payload.memory_truncated,
        "event_truncated_count": payload.event_truncated_count,
        "history_truncated_count": payload.history_truncated_count,
        "run_observation_truncated_count": payload.run_observation_truncated_count,
    }


def _routing_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the ``decision_routed`` payload into governance's routing block."""
    events = _scoped_events(
        observations,
        boundary=_DECISION_BOUNDARY,
        kinds=("decision_routed",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[0].payload
    return {
        "routed": payload.routed,
        "interaction_scope_kind": payload.interaction_scope_kind,
        "response_domain": payload.response_domain,
        "response_channel_id": payload.response_channel_id,
        "response_conversation_id": payload.response_conversation_id,
        "memory_eligible": payload.memory_eligible,
    }


def _memory_writeback_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the settlement-time ``memory.encode`` payloads (Gap 7)."""
    events = _scoped_events(
        observations,
        boundary=_MEMORY_ENCODE_BOUNDARY,
        kinds=("encode_candidate", "encode_commit", "reinforcement_applied"),
        frame_id=frame_id,
    )
    candidates: List[Dict[str, Any]] = []
    commits: List[Dict[str, Any]] = []
    reinforcements: List[Dict[str, Any]] = []
    for event in events:
        payload = event.payload
        if event.kind == "encode_candidate":
            candidates.append(
                {
                    "candidate_id": payload.candidate_id,
                    "base_revision": payload.base_revision,
                    "source_event_ids": list(payload.source_event_ids),
                    "emotion": payload.emotion,
                    "intensity": payload.intensity,
                    "content_chars": payload.content_chars,
                }
            )
        elif event.kind == "encode_commit":
            commits.append(
                {
                    "candidate_id": payload.candidate_id,
                    "episode_id": payload.episode_id,
                    "status": payload.status,
                    "reason": payload.reason,
                    "revision_before": payload.revision_before,
                    "revision_after": payload.revision_after,
                }
            )
        else:
            reinforcements.append(
                {
                    "event_id": payload.event_id,
                    "target_kind": payload.target_kind,
                    "target_id": payload.target_id,
                    "outcome_kind": payload.outcome_kind,
                    "accepted": payload.accepted,
                    "reason": payload.reason,
                    "revision_before": payload.revision_before,
                    "revision_after": payload.revision_after,
                }
            )
    if not candidates and not commits and not reinforcements:
        return None
    return {
        "candidates": candidates,
        "commits": commits,
        "reinforcements": reinforcements,
    }


def _emotion_changes_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the final ``emotion_candidate`` payload (Gap 7).

    A turn computes at most a fast and a slow candidate; the last one in
    emit order is the candidate the turn settled with.
    """
    events = _scoped_events(
        observations,
        boundary=_EMOTION_BOUNDARY,
        kinds=("emotion_candidate",),
        frame_id=frame_id,
    )
    if not events:
        return None
    payload = events[-1].payload
    return {
        "stage": payload.stage,
        "revision": payload.revision,
        "dimensions": [
            {"name": item.name, "before": item.before, "after": item.after}
            for item in payload.dimensions
        ],
        "changed_dimensions": list(payload.changed_dimensions),
    }


def _energy_state_view(budget: Any) -> Dict[str, Any]:
    """Project one Energy budget snapshot into raw scalar fields."""
    return {
        "energy": budget.energy,
        "fatigue": budget.fatigue,
        "cognitive_mode": budget.cognitive_mode,
        "long_reasoning_allowed": budget.long_reasoning_allowed,
        "available_cognitive_budget": budget.available_cognitive_budget,
        "reserved_cognitive_budget": budget.reserved_cognitive_budget,
    }


def _energy_settlement_block(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Optional[Dict[str, Any]]:
    """Project the ``budget_settled``/``budget_released`` payloads (Gap 7)."""
    settled = _scoped_events(
        observations,
        boundary=_ENERGY_BOUNDARY,
        kinds=("budget_settled",),
        frame_id=frame_id,
    )
    released = _scoped_events(
        observations,
        boundary=_ENERGY_BOUNDARY,
        kinds=("budget_released",),
        frame_id=frame_id,
    )
    if not settled and not released:
        return None
    budget = None
    if settled:
        budget = settled[-1].payload.budget
    elif released:
        budget = released[-1].payload.budget
    return {
        "consumed": settled[-1].payload.consumed if settled else None,
        "charged": settled[-1].payload.charged if settled else None,
        "released": released[-1].payload.released if released else None,
        "energy_state": _energy_state_view(budget) if budget is not None else None,
    }


def build_observability_trace(
    *,
    turn_id: str,
    stimulus: Mapping[str, Any],
    state_before: Mapping[str, Any],
    state_after: Mapping[str, Any],
    state_diff: Mapping[str, Any],
    raw_stages: Mapping[str, Any],
    result: Mapping[str, Any],
    decision: Mapping[str, Any],
    duration_ms: float,
    warnings: Iterable[Any] = (),
    observations: Sequence[BrainObservation] = (),
    workspace_checkpoint: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the seven top-level stages of one real production Turn.

    The projection intentionally keeps exact prompts, model responses and
    snapshots in their source-shaped fields.  The frontend decides which of
    those fields are visible by default; it never has to invent missing
    evidence from a label or a count.
    """

    stages = _mapping(raw_stages)
    reasoning = _mapping(stages.get("reasoning"))
    boundary = _mapping(stages.get("turn_boundary"))
    cognitive_turn = _mapping(stages.get("cognitive_turn"))
    typed_input = _mapping(stages.get("typed_input"))
    receipts = list(_sequence(stages.get("output_receipts")))
    frame_id = cognitive_turn.get("frame_id")
    memory = _memory_view(observations, frame_id=frame_id)
    compiles = _turn_compiles(observations, frame_id=frame_id)
    trims = _turn_context_trims(observations, frame_id=frame_id)
    model_calls = _turn_model_calls(observations, frame_id=frame_id)
    completion_events = [
        event
        for event in observations
        if event.boundary == "reasoning.completion"
        and event.kind == "judge"
        and (not frame_id or str(event.frame_id) == str(frame_id))
    ]
    first_request = _model_request_view(model_calls[0]) if model_calls else {}
    stage_durations = {
        stage_id: _stage_duration(observations, members, frame_id=frame_id)
        for stage_id, members in _STAGE_EVENT_MEMBERS.items()
    }

    appended = _appended_block(observations, frame_id=frame_id)
    current_event_ids = _context_current_event_ids(appended, decision)
    context_frozen = _context_frozen_block(observations, frame_id=frame_id)

    setup = _setup_stage(
        turn_id=turn_id,
        stimulus=stimulus,
        state_before=state_before,
        request=first_request,
        baseline_memory=memory["baseline_memory"],
        mode_selection=_mode_selection_block(observations, frame_id=frame_id),
        budget=_budget_block(observations, frame_id=frame_id),
        selfhood_projection=_selfhood_projection_block(observations, frame_id=frame_id),
        context_frozen=context_frozen,
        duration_ms=stage_durations["setup"],
    )
    reasoning_stage = _reasoning_stage(
        reasoning=reasoning,
        loop_events=[
            *_turn_agent_loop_events(observations, frame_id=frame_id),
            *[_event_dump(event) for event in completion_events],
        ],
        terminal_events=_turn_agent_loop_terminal_events(
            observations, frame_id=frame_id
        ),
        compiles=compiles,
        trims=trims,
        duration_ms=stage_durations["reasoning_run"],
    )

    return {
        "schema_version": 1,
        "source": "production_turn_record",
        "duration_ms": duration_ms,
        "chain": [
            _event_admission_stage(
                turn_id=turn_id,
                stimulus=stimulus,
                typed_input=typed_input,
                boundary=boundary,
                cognitive_turn=cognitive_turn,
                admission=_admission_block(observations, frame_id=frame_id),
                duration_ms=stage_durations["event_admission"],
            ),
            _context_workspace_stage(
                turn_id=turn_id,
                stimulus=stimulus,
                request=first_request,
                compiles=compiles,
                appended=appended,
                current_event_ids=current_event_ids,
                workspace_checkpoint=workspace_checkpoint,
                duration_ms=stage_durations["context_workspace"],
            ),
            setup,
            reasoning_stage,
            _decision_stage(
                decision=decision,
                reasoning=reasoning,
                calls=model_calls,
                duration_ms=stage_durations["turn_decision"],
            ),
            _governance_stage(
                decision=decision,
                result=result,
                receipts=receipts,
                routing=_routing_block(observations, frame_id=frame_id),
                duration_ms=stage_durations["governance_delivery"],
            ),
            _settlement_stage(
                turn_id=turn_id,
                result=result,
                receipts=receipts,
                state_after=state_after,
                state_diff=state_diff,
                cognitive_turn=cognitive_turn,
                memory_writeback=_memory_writeback_block(
                    observations, frame_id=frame_id
                ),
                emotion_changes=_emotion_changes_block(observations, frame_id=frame_id),
                energy_settlement=_energy_settlement_block(
                    observations, frame_id=frame_id
                ),
                duration_ms=duration_ms,
                stage_duration_ms=stage_durations["settlement"],
                warnings=warnings,
            ),
        ],
        "memory": memory["block"],
    }


def _memory_view(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> Dict[str, Any]:
    """Rebuild the memory view from raw ``BrainObservation`` envelopes.

    The first ``recall_result`` of the turn's frame is the baseline recall;
    every later result is an on-demand recall.  Only raw values carried by
    the envelopes are shown: the observation stream records recalled
    material as typed IDs and counts, not as text, so ``returned_evidence``
    stays empty and the evidence points carry record IDs.
    """

    bridge = [
        event for event in observations if event.boundary == _MEMORY_BRIDGE_BOUNDARY
    ]
    if frame_id:
        scoped = [event for event in bridge if event.frame_id == frame_id]
        if scoped:
            bridge = scoped
    turn_opened = next(
        (event for event in bridge if event.kind == "turn_opened"),
        None,
    )
    recall_results = [event for event in bridge if event.kind == "recall_result"]
    baseline_event = recall_results[0] if recall_results else None
    on_demand_events = recall_results[1:]
    opened = turn_opened.payload if turn_opened is not None else None
    baseline = baseline_event.payload if baseline_event is not None else None

    status = "unavailable"
    query = ""
    revision: Any = None
    reason: Optional[str] = None
    points: List[Dict[str, Any]] = []
    if baseline is not None:
        bundle = baseline.bundle
        status = baseline.status
        query = opened.query if opened is not None else baseline.query
        revision = (
            bundle.recall_revision if bundle is not None else baseline.pinned_revision
        )
        reason = baseline.reason
        points = _bundle_points(bundle)
    elif opened is not None:
        query = opened.query
        revision = opened.pinned_revision

    block = {
        "status": status,
        "query": query,
        "revision": revision,
        "reason": reason,
        "returned_evidence": "",
        "returned_points": points,
        "selected": _selected_memory(observations),
        "on_demand": [_on_demand_entry(event) for event in on_demand_events],
        "raw": {
            "source": "brain_observations",
            "turn_opened": _event_dump(turn_opened),
            "baseline": _event_dump(baseline_event),
            "on_demand": [_event_dump(event) for event in on_demand_events],
        },
    }
    baseline_memory = {
        "status": status,
        "query": query,
        "revision": revision,
        "reason": reason,
        "returned_evidence": "",
        "returned_points": points,
        "evidence_basis": "brain_observations.reasoning.memory_bridge",
    }
    return {"block": block, "baseline_memory": baseline_memory}


def _bundle_points(bundle: Any) -> List[Dict[str, Any]]:
    """Render the recall bundle's typed IDs as honest evidence points."""
    if bundle is None:
        return []
    points: List[Dict[str, Any]] = []
    for point_id in bundle.focus_node_ids:
        points.append({"kind": "focus_node", "id": point_id, "evidence": point_id})
    for point_id in bundle.assertion_ids:
        points.append({"kind": "assertion", "id": point_id, "evidence": point_id})
    for point_id in bundle.episode_ids:
        points.append({"kind": "episode", "id": point_id, "evidence": point_id})
    for point_id in bundle.evidence_ids:
        points.append({"kind": "evidence", "id": point_id, "evidence": point_id})
    return points


def _selected_memory(
    observations: Sequence[BrainObservation],
) -> List[Dict[str, Any]]:
    """Project the ``memory.encode`` use-proposal events (selected memory)."""
    selected: List[Dict[str, Any]] = []
    for event in observations:
        if (
            event.boundary != _MEMORY_ENCODE_BOUNDARY
            or event.kind != "use_proposal_recorded"
        ):
            continue
        payload = event.payload
        selected.append(
            {
                "proposal_id": payload.proposal_id,
                "target_kind": payload.target_kind,
                "target_ids": list(payload.target_ids),
                "recall_revision": payload.recall_revision,
                "accepted": payload.accepted,
                "reason": payload.reason,
            }
        )
    return selected


def _on_demand_entry(event: BrainObservation) -> Dict[str, Any]:
    payload = event.payload
    bundle = payload.bundle
    return {
        "status": payload.status,
        "query": payload.query,
        "reason": payload.reason,
        "revision": (
            bundle.recall_revision if bundle is not None else payload.pinned_revision
        ),
        "returned_evidence": "",
        "returned_points": _bundle_points(bundle),
        "raw": _event_dump(event),
    }


def _event_dump(event: Optional[BrainObservation]) -> Optional[Dict[str, Any]]:
    if event is None:
        return None
    return event.model_dump(mode="json")


def _turn_compiles(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> List[BrainObservation]:
    compiles = [
        event
        for event in observations
        if event.boundary == _CONTEXT_ENGINE_BOUNDARY
        and event.kind == "compiled_context"
    ]
    if frame_id:
        compiles = [event for event in compiles if str(event.frame_id) == str(frame_id)]
    return compiles


def _turn_model_calls(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> List[Dict[str, Any]]:
    """Dump the turn's ``model_call`` envelopes in emit order.

    Model I/O evidence comes from the Brain's ``reasoning.agent_loop`` /
    ``model_call`` observations — the single semantic record of every
    ModelPort call.  When the turn frame is known, envelopes of other frames
    are dropped so a concurrent autonomous turn cannot leak into this view.
    """
    events = [
        event
        for event in observations
        if event.boundary == _AGENT_LOOP_BOUNDARY and event.kind == "model_call"
    ]
    if frame_id:
        events = [event for event in events if str(event.frame_id) == str(frame_id)]
    return [_event_dump(event) for event in events]


def _turn_agent_loop_events(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> List[Dict[str, Any]]:
    """Dump the per-iteration agent-loop envelopes in emit order.

    Covers exactly ``_AGENT_LOOP_ITERATION_KINDS`` — the envelopes whose
    payloads carry ``iteration_index``.  Run-level terminal records
    (``guard_stop``, ``run_failed``) have no key and stay out of the buckets.
    """
    events = [
        event
        for event in observations
        if event.boundary == _AGENT_LOOP_BOUNDARY
        and event.kind in _AGENT_LOOP_ITERATION_KINDS
    ]
    if frame_id:
        events = [event for event in events if str(event.frame_id) == str(frame_id)]
    return [_event_dump(event) for event in events]


def _turn_agent_loop_terminal_events(
    observations: Sequence[BrainObservation],
    *,
    frame_id: Any,
) -> List[Dict[str, Any]]:
    """Dump run-level agent-loop closure records for raw trace evidence."""
    events = [
        event
        for event in observations
        if event.boundary == _AGENT_LOOP_BOUNDARY
        and event.kind in {"guard_stop", "run_failed"}
    ]
    if frame_id:
        events = [event for event in events if str(event.frame_id) == str(frame_id)]
    return [_event_dump(event) for event in events]


def _iteration_buckets(
    events: Sequence[Mapping[str, Any]],
) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    """Group agent-loop envelopes by their own ``payload.iteration_index``.

    Envelopes arrive in sequence (emit) order, so each bucket list keeps the
    emit order inside one iteration.  Envelopes without a usable integer key
    cannot join a bucket and are ignored.
    """
    buckets: Dict[int, Dict[str, List[Dict[str, Any]]]] = {}
    for event in events:
        payload = _mapping(event.get("payload"))
        raw_index = payload.get("iteration_index")
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            continue
        kind = str(event.get("kind", ""))
        bucket = buckets.setdefault(raw_index, {})
        bucket.setdefault(kind, []).append(dict(event))
    return buckets


def _model_request_view(event_dump: Mapping[str, Any]) -> Dict[str, Any]:
    """Project one model_call envelope into the request view the chain shows."""
    payload = _mapping(event_dump.get("payload"))
    return {
        "frame_id": event_dump.get("frame_id"),
        "system_prompt": payload.get("system_prompt"),
        "user_prompt": payload.get("user_prompt"),
        "context_revision": payload.get("context_revision"),
        "capability_revision": payload.get("capability_revision"),
        "reasoning_mode": payload.get("reasoning_mode"),
        "response_mode": payload.get("response_mode"),
        "response_schema_name": payload.get("response_schema_name"),
        "response_schema": payload.get("response_schema"),
        "temperature": payload.get("temperature"),
        "max_tokens": payload.get("max_tokens"),
        "timeout_seconds": payload.get("timeout_seconds"),
        "allowed_tools": payload.get("allowed_tools"),
        "tool_definition_count": payload.get("tool_definition_count"),
        "skill_count": payload.get("skill_count"),
    }


def _compiled_summary(payload: Any) -> Dict[str, Any]:
    return {
        "context_revision": payload.context_revision,
        "capability_revision": payload.capability_revision,
        "memory_recall_revision": payload.memory_recall_revision,
        "max_tokens": payload.max_tokens,
        "reasoning_mode": payload.reasoning_mode,
        "response_mode": payload.response_mode,
        "event_count": payload.event_count,
        "state_update_count": payload.state_update_count,
        "media_sample_count": payload.media_sample_count,
        "conversation_count": payload.conversation_count,
        "summary_count": payload.summary_count,
        "run_observation_count": payload.run_observation_count,
        "memory_chars": payload.memory_chars,
        "memory_estimated_tokens": payload.memory_estimated_tokens,
        "truncated": payload.truncated,
    }


def _workspace_message_view(
    value: Any,
    *,
    current_event_ids: Sequence[Any] = (),
) -> Dict[str, Any]:
    """Project one persisted conversation message with a readable speaker.

    ``ConversationMessage.sender`` is an ``ActorRef`` in the Brain contract;
    the Lab derives a short read-side label from the source category and
    optional display name.  Actor identity remains available as secondary
    provenance, but is never the primary history label.  The event id remains
    in the projection for provenance, while the UI can use ``is_current`` to
    keep the current input in Event Workspace only.
    """
    message = _mapping(value)
    sender = _mapping(message.get("sender"))
    event_id = message.get("event_id")
    current_ids = {str(item) for item in current_event_ids}
    source_kind = sender.get("source_kind") or message.get("source_kind")
    display_name = sender.get("display_name") or message.get("display_name")
    actor_id = sender.get("actor_id") or message.get("actor_id")
    return {
        "event_id": event_id,
        "speaker": _speaker_label(
            source_kind=source_kind,
            display_name=display_name,
            actor_id=actor_id,
        ),
        "speaker_kind": source_kind,
        "actor_id": actor_id,
        "display_name": display_name,
        "content": message.get("content"),
        "occurred_at": _iso_utc(message.get("occurred_at")),
        "is_current": (event_id is not None and str(event_id) in current_ids),
    }


def _workspace_summary_view(value: Any) -> Dict[str, Any]:
    """Project one source-linked Context Workspace compression summary."""
    summary = _mapping(value)
    return {
        "summary_id": summary.get("summary_id"),
        "version": summary.get("version"),
        "source_event_ids": list(_sequence(summary.get("source_event_ids"))),
        "occurred_from": _iso_utc(summary.get("occurred_from")),
        "occurred_to": _iso_utc(summary.get("occurred_to")),
        "content": summary.get("content"),
        "unresolved_items": list(_sequence(summary.get("unresolved_items"))),
    }


def _workspace_topic_view(
    value: Any,
    *,
    current_event_ids: Sequence[Any] = (),
) -> Optional[Dict[str, Any]]:
    """Project actual topic state as lifecycle metadata, not a fake title."""
    topic = _mapping(value)
    if not topic:
        return None
    messages = [
        _workspace_message_view(item, current_event_ids=current_event_ids)
        for item in _sequence(topic.get("messages"))
    ]
    summaries = [
        _workspace_summary_view(item) for item in _sequence(topic.get("summaries"))
    ]
    close_after = topic.get("close_after_event_id")
    return {
        "state": "待关闭" if close_after else "活跃",
        "participants": list(_sequence(topic.get("participants"))),
        "started_at": _iso_utc(topic.get("started_at")),
        "last_activity_at": _iso_utc(topic.get("last_activity_at")),
        "pending_close": bool(close_after),
        "message_count": len(messages),
        "summary_count": len(summaries),
        "messages": messages,
        "summaries": summaries,
    }


def _workspace_pending_reply_view(value: Any) -> Dict[str, Any]:
    """Project a reply that is persisted until a delivery receipt settles it."""
    reply = _mapping(value)
    return {
        "status": "待回执",
        "channel_id": reply.get("channel_id"),
        "conversation_id": reply.get("conversation_id"),
        "content": reply.get("content"),
        "prepared_at": _iso_utc(reply.get("prepared_at")),
        "memory_eligible": reply.get("memory_eligible"),
        "cause_event_ids": list(_sequence(reply.get("cause_event_ids"))),
        "intent_id": reply.get("intent_id"),
        "reply_event_id": reply.get("reply_event_id"),
    }


def _workspace_pending_episode_view(value: Any) -> Dict[str, Any]:
    """Project a pending ClosedEpisode payload without parsing prompt text."""
    episode = _mapping(value)
    if not episode and isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            parsed = {}
        episode = _mapping(parsed)
    return {
        "status": "待写入 Memory",
        "event_kind": episode.get("event_kind"),
        "occurred_from": episode.get("occurred_from"),
        "occurred_to": episode.get("occurred_to"),
        "content_text": episode.get("content_text"),
        "summary_text": episode.get("summary_text"),
        "stimulus": episode.get("stimulus"),
        "sensory": list(_sequence(episode.get("sensory"))),
        "metadata": _mapping(episode.get("metadata")),
        "source_event_ids": list(_sequence(episode.get("source_event_ids"))),
        "episode_id": episode.get("episode_id"),
    }


def _workspace_checkpoint_projection(
    checkpoint: Any,
    *,
    current_event_ids: Sequence[Any] = (),
) -> Optional[Dict[str, Any]]:
    """Map the real conversation checkpoint into displayable workspace state.

    This is intentionally a read-side projection over the persisted
    ``ConversationContextCheckpoint``.  It carries every bounded message and
    summary, plus active/pending lifecycle state and deferred handoffs.  The
    exact checkpoint is retained under the stage's ``raw`` record.
    """
    if checkpoint is None:
        return None
    if not isinstance(checkpoint, Mapping):
        model_dump = getattr(checkpoint, "model_dump", None)
        if callable(model_dump):
            checkpoint = model_dump(mode="json")
    source = _mapping(checkpoint)
    if not source and checkpoint not in ({}, None):
        return None

    threads: List[Dict[str, Any]] = []
    for value in _sequence(source.get("threads")):
        thread = _mapping(value)
        messages = [
            _workspace_message_view(item, current_event_ids=current_event_ids)
            for item in _sequence(thread.get("messages"))
        ]
        summaries = [
            _workspace_summary_view(item) for item in _sequence(thread.get("summaries"))
        ]
        active_state = _workspace_topic_view(
            thread.get("active_topic"),
            current_event_ids=current_event_ids,
        )
        pending_states = [
            state
            for state in (
                _workspace_topic_view(
                    item,
                    current_event_ids=current_event_ids,
                )
                for item in _sequence(thread.get("pending_topics"))
            )
            if state is not None
        ]
        threads.append(
            {
                "channel_id": thread.get("channel_id"),
                "conversation_id": thread.get("conversation_id"),
                "messages": messages,
                "summaries": summaries,
                "active_state": active_state,
                "pending_states": pending_states,
            }
        )

    pending_replies = [
        _workspace_pending_reply_view(item)
        for item in _sequence(source.get("pending_replies"))
    ]
    pending_memory = [
        _workspace_pending_episode_view(item)
        for item in _sequence(source.get("pending_closed_episode_payloads"))
    ]
    return {
        "threads": threads,
        "pending_replies": pending_replies,
        "pending_memory": pending_memory,
        "checkpoint": {
            "status": "已保存",
            "thread_count": len(threads),
            "pending_reply_count": len(pending_replies),
            "pending_memory_count": len(pending_memory),
        },
    }


def _speaker_label(
    *,
    source_kind: Any = None,
    display_name: Any = None,
    actor_id: Any = None,
) -> str:
    """Return a semantic history label without exposing opaque actor IDs.

    ``display_name`` is the strongest existing human-readable fact unless it
    is one of the old generic labels.  When it is absent, the stable
    ``ActorRef.source_kind`` category supplies the two Lab-facing labels
    ``开发者`` and ``elfie``.  Unknown/legacy actors collapse to ``elfie`` in
    this two-party Lab view rather than leaking an implementation identifier;
    the raw record still retains ``actor_id``.
    """
    if isinstance(display_name, str) and display_name.strip():
        normalized_display = display_name.strip()
        if normalized_display in {"主人", "人类参与者", "开发者输入", "调试输入"}:
            return "开发者"
        if normalized_display in {"Elfie", "精灵", "小精灵", "未命名精灵"}:
            return "elfie"
        return normalized_display

    kind = source_kind.strip().lower() if isinstance(source_kind, str) else ""
    labels = {
        "owner": "开发者",
        "elfie": "elfie",
        "developer_tool": "开发者",
        "human": "开发者",
        "system": "系统",
        "activity": "Activity",
        "microphone": "麦克风",
        "vision": "视觉输入",
        "touch": "触觉输入",
        "environment": "环境输入",
        "body": "身体输入",
        "internal": "内部事件",
    }
    if kind in labels:
        return labels[kind]
    # The Lab currently has only the developer and the current Elfie in this
    # projection.  If an older row lost its source kind, keep it readable and
    # attach it to Elfie rather than exposing an abstract participant label.
    if kind or actor_id:
        return "elfie"
    return "elfie"


def _compiled_conversation_rows(
    payload: Any,
    *,
    current_event_ids: Sequence[Any] = (),
) -> List[Dict[str, Any]]:
    """Project the compiled conversation rows carried by the payload.

    Rows come from the ``compiled_context`` envelope payload's raw
    ``conversation`` tuples — the exact prior-turn rows the Context Engine
    kept — never from parsing prompt text.  The read-side speaker label uses
    the same semantic source-category mapping as checkpoint messages; raw
    actor identity remains secondary provenance.
    """
    rows: List[Dict[str, Any]] = []
    for row in getattr(payload, "conversation", ()) or ():
        display_name = getattr(row, "display_name", None)
        source_kind = getattr(row, "source_kind", None)
        actor_id = getattr(row, "actor_id", None)
        event_id = getattr(row, "event_id", None)
        current_ids = {str(item) for item in current_event_ids}
        rows.append(
            {
                "event_id": event_id,
                "speaker": _speaker_label(
                    source_kind=source_kind,
                    display_name=display_name,
                    actor_id=actor_id,
                ),
                "speaker_kind": source_kind,
                "actor_id": actor_id,
                "display_name": display_name,
                "content": row.content,
                "occurred_at": _iso_utc(row.occurred_at),
                "is_current": (event_id is not None and str(event_id) in current_ids),
            }
        )
    return rows


def _compiled_sections(payload: Any) -> List[str]:
    """List the compiled sections that actually carry data.

    Derived only from the payload's raw counts and conversation rows; the
    conversation section counts a row even when a pre-rows payload only
    carries ``conversation_count``.
    """
    sections: List[str] = []
    if payload.event_count:
        sections.append("events")
    if payload.state_update_count:
        sections.append("state_updates")
    if payload.media_sample_count:
        sections.append("media_samples")
    if getattr(payload, "conversation", ()) or payload.conversation_count:
        sections.append("conversation")
    if payload.summary_count:
        sections.append("context_summaries")
    if payload.run_observation_count:
        sections.append("run_observations")
    if payload.memory_chars:
        sections.append("memory")
    return sections


def _iso_utc(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _number_text(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{value:g}"


def _admission_modality_values(
    stimulus: Mapping[str, Any],
    *,
    source_domain: Any,
    modalities: Sequence[Any],
) -> Dict[str, str]:
    """Project user-readable values for the input modalities in this Turn.

    The first stage is a Lab-facing input summary, so it keeps the submitted
    value (message, media type, touch and temperature) without exposing the
    internal frame IDs or trigger metrics that remain available in ``raw``.
    """
    domain = str(source_domain or "")
    names = {str(item) for item in modalities if isinstance(item, str)}
    message = stimulus.get("message")
    message_text = message.strip() if isinstance(message, str) else ""
    values: Dict[str, str] = {}

    if domain == "communication":
        if message_text or "text" in names:
            values["text"] = message_text
        attachments = [
            _mapping(item) for item in _sequence(stimulus.get("message_attachments"))
        ]
        if attachments or "attachment" in names:
            filenames = [
                str(item["filename"]) for item in attachments if item.get("filename")
            ]
            values["attachment"] = (
                "、".join(filenames) if filenames else f"{len(attachments)} 个附件"
            )
        return values

    if message_text or "hearing" in names:
        values["hearing"] = message_text

    media = _mapping(stimulus.get("vision_media"))
    if media or "vision" in names:
        mime_type = media.get("mime_type")
        values["vision"] = (
            f"已提供视觉输入（{mime_type}）" if mime_type else "已提供视觉输入"
        )

    if "environment" in names:
        temperature = _number_text(stimulus.get("temperature"))
        values["environment"] = (
            f"温度 {temperature}°C" if temperature is not None else "已提供环境输入"
        )

    impact = _number_text(stimulus.get("impact_force"))
    stroke = _number_text(stimulus.get("gentle_stroke"))
    if "touch" in names or (impact not in (None, "0") or stroke not in (None, "0")):
        location = stimulus.get("impact_direction")
        location_text = (
            str(location)
            if isinstance(location, str) and location and location != "none"
            else ""
        )
        force = max(
            value
            for value in (
                float(impact) if impact is not None else 0.0,
                float(stroke) if stroke is not None else 0.0,
            )
        )
        force_text = _number_text(force)
        values["touch"] = (
            " · ".join(
                item
                for item in (
                    location_text,
                    f"力度 {force_text}" if force_text is not None else None,
                )
                if item
            )
            or "已提供触觉输入"
        )
    return values


def _compile_index_for_revision(
    compiles: Sequence[BrainObservation],
    context_revision: Any,
) -> Optional[int]:
    for index, event in enumerate(compiles):
        if event.payload.context_revision == context_revision:
            return index
    return None


def _event_admission_stage(
    *,
    turn_id: str,
    stimulus: Mapping[str, Any],
    typed_input: Mapping[str, Any],
    boundary: Mapping[str, Any],
    cognitive_turn: Mapping[str, Any],
    admission: Optional[Mapping[str, Any]],
    duration_ms: Optional[float],
) -> Dict[str, Any]:
    source_domain = stimulus.get("source_domain") or typed_input.get("source_domain")
    modalities = list(_sequence(typed_input.get("modalities")))
    return {
        "number": "1",
        "id": "event_admission",
        "title": "Event admission",
        "status": "completed" if stimulus or typed_input else "unavailable",
        "duration_ms": duration_ms,
        "input": {
            "source_domain": source_domain,
            "message": stimulus.get("message", ""),
            "modalities": modalities,
            "modality_values": _admission_modality_values(
                stimulus,
                source_domain=source_domain,
                modalities=modalities,
            ),
        },
        "output": {
            "turn_id": cognitive_turn.get("turn_id") or turn_id,
            "frame_id": cognitive_turn.get("frame_id"),
            "source_domain": source_domain,
            "interaction_scope": boundary.get("interaction_scope"),
            "response_scope": boundary.get("response_scope"),
            "status": cognitive_turn.get("status"),
        },
        "admission": dict(admission) if admission is not None else None,
        "raw": {
            "typed_input": typed_input,
            "turn_boundary": boundary,
            "cognitive_turn": cognitive_turn,
        },
    }


def _context_workspace_stage(
    *,
    turn_id: str,
    stimulus: Mapping[str, Any],
    request: Mapping[str, Any],
    compiles: Sequence[BrainObservation],
    appended: Optional[Mapping[str, Any]],
    current_event_ids: Sequence[Any],
    workspace_checkpoint: Optional[Mapping[str, Any]],
    duration_ms: Optional[float],
) -> Dict[str, Any]:
    first_compile = compiles[0].payload if compiles else None
    output: Dict[str, Any] = {
        "context_revision": request.get("context_revision"),
        "frame_id": request.get("frame_id"),
    }
    if first_compile is not None:
        # No "compiled" summary here: per-call compiles render in the
        # ReasoningRun iterations' context_build, keyed by context_revision.
        output["conversation"] = _compiled_conversation_rows(
            first_compile,
            current_event_ids=current_event_ids,
        )
        # Run-observation content exists only as payload counts: these keys
        # stay null rather than being reconstructed from prompt text (P1).
        output["current_observations"] = None
        output["current_run_observations"] = None
    workspace = _workspace_checkpoint_projection(
        workspace_checkpoint,
        current_event_ids=current_event_ids,
    )
    if workspace is not None:
        output["workspace"] = workspace
    return {
        "number": "2",
        "id": "context_workspace",
        "title": "Context Workspace",
        "status": (
            "completed"
            if (
                request
                or compiles
                or appended is not None
                or workspace_checkpoint is not None
            )
            else "unavailable"
        ),
        "duration_ms": duration_ms,
        "input": {
            "turn_id": turn_id,
            "message": stimulus.get("message", ""),
        },
        "output": output,
        "appended": dict(appended) if appended is not None else None,
        "raw": {
            "source": "brain_observations.reasoning.agent_loop.model_call",
            "context_revision": request.get("context_revision"),
            "user_prompt": request.get("user_prompt"),
            "compiled_events": [_event_dump(event) for event in compiles],
            "workspace_checkpoint": (
                dict(workspace_checkpoint) if workspace_checkpoint is not None else None
            ),
            "workspace_checkpoint_source": (
                "brain_continuity_checkpoint"
                if workspace_checkpoint is not None
                else None
            ),
        },
    }


def _setup_stage(
    *,
    turn_id: str,
    stimulus: Mapping[str, Any],
    state_before: Mapping[str, Any],
    request: Mapping[str, Any],
    baseline_memory: Mapping[str, Any],
    mode_selection: Optional[Mapping[str, Any]],
    budget: Optional[Mapping[str, Any]],
    selfhood_projection: Optional[Mapping[str, Any]],
    context_frozen: Optional[Mapping[str, Any]],
    duration_ms: Optional[float],
) -> Dict[str, Any]:
    mode = mode_selection or {}
    setup_output = {
        "turn_id": turn_id,
        "source_domain": request.get("source_domain") or stimulus.get("source_domain"),
        "context_revision": request.get("context_revision"),
        "capability_revision": request.get("capability_revision"),
        # The Run Controller's typed mode decision is the closer record of
        # what this Run actually chose; the first-request fields only serve
        # as the fallback when the observation stream has no such envelope.
        "reasoning_mode": mode.get("reasoning_mode") or request.get("reasoning_mode"),
        "response_mode": mode.get("response_mode") or request.get("response_mode"),
        "response_schema": request.get("response_schema_name"),
        "temperature": request.get("temperature"),
        "max_tokens": request.get("max_tokens"),
        "depth": mode.get("depth"),
        "depth_basis": mode.get("depth_basis"),
        "requires_model": mode.get("requires_model"),
        "structured_owner_reply": mode.get("structured_owner_reply"),
        "fast_owner_reply": mode.get("fast_owner_reply"),
        "effective_tools": mode.get("effective_tools"),
        "skill_count": mode.get("skill_count"),
    }
    return {
        "number": "3",
        "id": "setup",
        "title": "Setup",
        "status": "completed"
        if state_before or request or context_frozen
        else "unavailable",
        "duration_ms": duration_ms,
        "input": {
            "turn_id": turn_id,
            "source_domain": stimulus.get("source_domain"),
        },
        "output": setup_output,
        "budget": dict(budget) if budget is not None else None,
        "selfhood_projection": (
            dict(selfhood_projection) if selfhood_projection is not None else None
        ),
        "frozen_state": (dict(context_frozen) if context_frozen is not None else None),
        "owner_snapshots": _owner_snapshots(context_frozen),
        "baseline_memory": baseline_memory,
        "raw": {
            "state_before": dict(state_before),
            "request": dict(request),
            "context_frozen": (
                dict(context_frozen) if context_frozen is not None else None
            ),
        },
    }


def _owner_snapshots(
    frozen_state: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if frozen_state is None:
        return []
    captured_at = frozen_state.get("context_captured_at")
    values = (
        ("orientation", "Orientation", frozen_state.get("orientation")),
        ("selfhood", "Selfhood", frozen_state.get("selfhood")),
        ("emotion", "Emotion", frozen_state.get("emotion")),
        ("energy", "Energy", frozen_state.get("homeostasis")),
        ("motivation", "Motivation", frozen_state.get("motivation")),
    )
    snapshots: List[Dict[str, Any]] = []
    for module_id, title, value in values:
        present = value is not None and (not isinstance(value, Mapping) or bool(value))
        snapshots.append(
            {
                "id": module_id,
                "title": title,
                "status": "recorded" if present else "unavailable",
                "input": {
                    "source_record": "reasoning.run_controller.context_frozen",
                    "captured_at": captured_at,
                    "context_revision": frozen_state.get("context_revision"),
                },
                "output": value,
                "raw": value,
                "evidence_basis": "reasoning.run_controller.context_frozen",
            }
        )
    return snapshots


def _reasoning_stage(
    *,
    reasoning: Mapping[str, Any],
    loop_events: Sequence[Mapping[str, Any]],
    terminal_events: Sequence[Mapping[str, Any]],
    compiles: Sequence[BrainObservation],
    trims: Sequence[BrainObservation],
    duration_ms: Optional[float],
) -> Dict[str, Any]:
    steps = [_mapping(step) for step in _sequence(reasoning.get("steps"))]
    groups = _iteration_groups(steps)
    buckets = _iteration_buckets(loop_events)
    # Iterations key on the model_call envelopes' own ``iteration_index``; the
    # other agent-loop envelopes join the key they were emitted with.  The
    # legacy ``steps`` array carries no keys, so it stays an ordered fallback
    # aligned by position for fields the envelopes do not carry.
    iteration_keys = sorted(
        key
        for key, bucket in buckets.items()
        if bucket.get("model_call") or bucket.get("guard")
    )
    iterations: List[Dict[str, Any]] = []
    iteration_count = max(len(iteration_keys), len(groups))
    for position in range(iteration_count):
        key = iteration_keys[position] if position < len(iteration_keys) else None
        bucket = buckets.get(key, {}) if key is not None else {}
        call_events = bucket.get("model_call", [])
        call = dict(call_events[0]) if call_events else {}
        payload = _mapping(call.get("payload"))
        group = groups[position] if position < len(groups) else []
        model_step = next(
            (step for step in group if str(step.get("kind", "")).lower() == "model"),
            {},
        )
        steps_observations = [
            step
            for step in group
            if str(step.get("kind", "")).lower() not in {"model", "verify"}
        ]
        typed_observations = [
            _observation_record_entry(event) for event in bucket.get("observation", ())
        ]
        observations = _merge_observation_records(
            steps_observations,
            typed_observations,
        )
        completions = [
            step for step in group if str(step.get("kind", "")).lower() == "verify"
        ]
        judge_events = bucket.get("judge", [])
        if judge_events:
            completions = [_judge_entry(event) for event in judge_events]
        action_event = next(iter(bucket.get("action_decoded", [])), None)
        action_payload = _mapping(action_event.get("payload")) if action_event else {}
        typed_result = _typed_action_result(action_payload)
        steps_result = _parsed_model_result(model_step)
        iteration_number = f"4.{position + 1}"
        model_call_number = f"{iteration_number}.2"
        # Trim events carry no iteration key, so each trim pairs with the
        # compile at the same emit-order position (1:1 per compile).  When
        # the counts diverge the pairing never guesses: a compile without a
        # positional trim renders none, and leftover trims stay at the
        # stage-level raw below.
        compile_index = _compile_index_for_revision(
            compiles,
            payload.get("context_revision"),
        )
        compile_payload = (
            compiles[compile_index].payload if compile_index is not None else None
        )
        context_output: Dict[str, Any] = {}
        if compile_payload is not None:
            # Keep revisions in the projection for causal correlation and the
            # raw-record view.  The human-facing Fields/Evidence renderer
            # filters these internal identifiers; the compiled prompt remains
            # the visible result of this slot.
            context_output["context_revision"] = compile_payload.context_revision
            context_output["capability_revision"] = compile_payload.capability_revision
            context_output["compiled"] = _compiled_summary(compile_payload)
            if compile_payload.system_prompt is not None:
                context_output["system_prompt"] = compile_payload.system_prompt
            if compile_payload.user_prompt is not None:
                context_output["user_prompt"] = compile_payload.user_prompt
        if compile_index is not None and compile_index < len(trims):
            trim_view = _trim_view(trims[compile_index].payload)
            context_output["trim"] = trim_view
        observation_stage = _observation_stage(
            number=f"{iteration_number}.4",
            observations=observations,
            duration_ms=_event_duration_sum(bucket.get("observation", [])),
        )
        # The ModelCall card keeps the wire-format parse the session chain pins;
        # the Cognitive Action card prefers the keyed envelope decode.
        model_call_parsed = steps_result if steps_result is not None else typed_result
        action_parsed = typed_result if typed_result is not None else steps_result
        # The six iteration slots are stable conceptual modules.  Completion
        # rows may be absent, but Guard must remain 4.1.6 rather than shifting
        # based on how many legacy verification rows happened to be present.
        guard_number = f"{iteration_number}.6"
        guard_event = (bucket.get("guard") or [None])[-1]
        guard_outcome = (
            _mapping(guard_event.get("payload")).get("outcome") if guard_event else None
        )
        iterations.append(
            {
                "number": iteration_number,
                "duration_ms": _event_duration_sum(
                    [
                        *call_events,
                        *bucket.get("action_decoded", []),
                        *bucket.get("observation", []),
                        *bucket.get("guard", []),
                        *judge_events,
                    ]
                ),
                "status": (
                    "failed"
                    if call and str(call.get("status")) == "failed"
                    else "completed"
                    if call
                    else guard_outcome
                    if guard_outcome in {"continued", "stopped"}
                    else "unavailable"
                ),
                "input": {},
                "context_build": {
                    "number": f"{iteration_number}.1",
                    "status": (
                        "compiled"
                        if compile_payload is not None
                        and (
                            compile_payload.system_prompt is not None
                            or compile_payload.user_prompt is not None
                        )
                        else "unavailable"
                    ),
                    "input": {},
                    "duration_ms": (
                        compiles[compile_index].duration_ms
                        if compile_index is not None
                        else None
                    ),
                    "output": context_output,
                    "raw": {
                        "compile_event": (
                            _event_dump(compiles[compile_index])
                            if compile_index is not None
                            else None
                        ),
                        "trim_event": (
                            _event_dump(trims[compile_index])
                            if compile_index is not None and compile_index < len(trims)
                            else None
                        ),
                    },
                }
                if compile_payload is not None
                else None,
                "model_call": (
                    _model_call_projection(
                        call,
                        number=model_call_number,
                        model_step=model_step,
                        parsed_result=model_call_parsed,
                    )
                    if call
                    else None
                ),
                "action": (
                    _action_projection(
                        number=f"{iteration_number}.3",
                        model_call_number=model_call_number,
                        parsed_result=action_parsed,
                        model_step=model_step,
                        action_event=action_event,
                    )
                    if action_event is not None or model_step
                    else None
                ),
                "observations": [dict(step) for step in observations],
                "observation_stage": observation_stage,
                "completion": completions,
                "guard": _guard_projection(
                    event=guard_event,
                    number=guard_number,
                ),
                "raw": {
                    "steps": group,
                    "model_call": dict(call) if call else None,
                    "source": "production_turn_record",
                    "iteration_index": key,
                },
            }
        )

    if not iterations and steps:
        iterations.append(
            {
                "number": "4.1",
                "status": "completed" if reasoning.get("status") else "unavailable",
                "input": {},
                "context_build": None,
                "model_call": None,
                "observations": [
                    step
                    for step in steps
                    if str(step.get("kind", "")).lower() != "verify"
                ],
                "completion": [
                    step
                    for step in steps
                    if str(step.get("kind", "")).lower() == "verify"
                ],
            }
        )
        iterations[0]["observation_stage"] = _observation_stage(
            number="4.1.4",
            observations=iterations[0]["observations"],
            duration_ms=None,
        )

    report = _mapping(_mapping(reasoning.get("decode")).get("report"))
    reasoning_raw = dict(reasoning)
    if terminal_events:
        reasoning_raw["terminal_events"] = [dict(event) for event in terminal_events]
    leftover_trims = trims[len(compiles) :]
    if leftover_trims:
        reasoning_raw["context_trims_unpaired"] = [
            _trim_view(event.payload) for event in leftover_trims
        ]
    return {
        "number": "4",
        "id": "reasoning_run",
        "title": "ReasoningRun",
        "status": reasoning.get("status", "unavailable"),
        "duration_ms": duration_ms,
        "iterations": iterations,
        "output": {
            "status": reasoning.get("status"),
            "model_calls": reasoning.get("model_calls"),
            "tool_calls": reasoning.get("tool_calls"),
            "skill_calls": reasoning.get("skill_calls"),
            "failure_reason": reasoning.get("failure_reason"),
            "selected_mode": report.get("selected_mode"),
            "fallback_reason": report.get("fallback_reason"),
            "terminal_reason": _terminal_reason(terminal_events),
        },
        "raw": reasoning_raw,
    }


def _merge_observation_records(
    legacy: Sequence[Mapping[str, Any]],
    typed: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep legacy display fields while attaching richer typed evidence.

    The legacy ``CognitiveStep`` rows carry readable operation/tool fields;
    typed observation envelopes carry source ids and revisions.  They are two
    views of the same records in current Brain runs, but a legacy tool request
    has a following observation row while the typed stream records only the
    latter.  Match semantic kinds and leave request-only rows untouched instead
    of blindly pairing by array position.
    """
    if not legacy:
        return [dict(item) for item in typed]
    if not typed:
        return [dict(item) for item in legacy]

    remaining_typed = [dict(item) for item in typed]
    merged: List[Dict[str, Any]] = []
    for legacy_item in legacy:
        row = dict(legacy_item)
        expected_kind = _legacy_observation_kind(row)
        match_index = (
            next(
                (
                    index
                    for index, item in enumerate(remaining_typed)
                    if _typed_observation_kind(item) == expected_kind
                ),
                None,
            )
            if expected_kind is not None
            else None
        )
        if match_index is not None:
            typed_item = remaining_typed.pop(match_index)
            if typed_item.get("kind") is not None:
                row["observation_kind"] = typed_item["kind"]
            if typed_item.get("status") is not None:
                row["observation_status"] = typed_item["status"]
            if not row.get("summary") and typed_item.get("summary"):
                row["summary"] = typed_item["summary"]
            if typed_item.get("source_ids"):
                row["source_ids"] = typed_item["source_ids"]
            if typed_item.get("revision") is not None:
                row["revision"] = typed_item["revision"]
            raw_legacy = row.get("raw")
            raw_typed = typed_item.get("raw")
            if raw_legacy is not None or raw_typed is not None:
                row["raw"] = {
                    "legacy_step": raw_legacy,
                    "observation_event": raw_typed,
                }
        merged.append(row)
    merged.extend(remaining_typed)
    return merged


def _typed_observation_kind(item: Mapping[str, Any]) -> Optional[str]:
    kind = item.get("kind")
    if not isinstance(kind, str) or not kind:
        return None
    # A stale memory recall is emitted as ``revision`` but still belongs to
    # the legacy ``operation=memory_recall`` row in the visible trace.
    return "memory" if kind == "revision" else kind


def _terminal_reason(events: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """Expose the latest run-level closure reason in the readable summary."""
    for event in reversed(events):
        payload = _mapping(event.get("payload"))
        kind = str(event.get("kind") or "")
        if kind == "run_failed":
            return str(payload.get("error_type") or "run_failed")
        reason = payload.get("reason") or payload.get("stop_reason")
        if reason is not None:
            return str(reason)
    return None


def _legacy_observation_kind(item: Mapping[str, Any]) -> Optional[str]:
    kind = str(item.get("kind") or "").lower()
    if kind == "skill":
        return "skill"
    if kind == "tool":
        # CognitiveStep records tool requests, whereas the typed stream emits
        # only the resulting observation.  The following legacy observation
        # row owns the typed ``tool`` envelope.
        return None
    if kind != "observation":
        return None
    operation = str(item.get("operation") or "")
    if operation == "memory_recall":
        return "memory"
    if operation == "activity_preflight":
        return "activity"
    if str(item.get("status") or "") == "invalid_cognitive_action":
        return "repair"
    if item.get("tool_key"):
        return "tool"
    return "observation"


def _model_call_projection(
    call: Mapping[str, Any],
    *,
    number: str,
    model_step: Mapping[str, Any],
    parsed_result: Any,
) -> Dict[str, Any]:
    """Project one Brain ``model_call`` observation envelope."""
    payload = _mapping(call.get("payload"))
    failed = bool(call) and str(call.get("status")) == "failed"
    response_text = payload.get("response_text")
    provider = payload.get("provider")
    model = payload.get("model_key")
    capability_view = {
        key: value
        for key, value in (
            ("tool_definitions", payload.get("tool_definitions")),
            ("available_skills", payload.get("available_skills")),
        )
        if value
    }
    projection: Dict[str, Any] = {
        "number": number,
        "status": "failed" if failed else "returned",
        "input": {
            "system_prompt": payload.get("system_prompt"),
            "user_prompt": payload.get("user_prompt"),
        },
        "output": {
            "response": response_text,
            "parsed_result": parsed_result,
            "provider": provider,
            "model": model,
            "selected_mode": payload.get("selected_mode"),
        },
        "effective_parameters": {
            "provider": provider,
            "model": model,
            "reasoning_mode": payload.get("reasoning_mode"),
            "response_mode": payload.get("response_mode"),
            "response_schema": payload.get("response_schema_name"),
            "response_schema_definition": payload.get("response_schema"),
            "temperature": payload.get("temperature"),
            "max_tokens": payload.get("max_tokens"),
            "timeout_seconds": payload.get("timeout_seconds"),
            "allowed_tools": payload.get("allowed_tools"),
            "tool_definition_count": payload.get("tool_definition_count"),
            "skill_count": payload.get("skill_count"),
            "context_revision": payload.get("context_revision"),
            "capability_revision": payload.get("capability_revision"),
        },
        "capabilities": capability_view or None,
        "duration_ms": call.get("duration_ms"),
        "prompt_tokens": payload.get("prompt_tokens"),
        "completion_tokens": payload.get("completion_tokens"),
        "provider_latency_ms": payload.get("provider_latency_ms"),
        "response": response_text,
        "reasoning_step": model_step,
        "raw": dict(call),
    }
    error = call.get("error")
    if error:
        projection["error"] = error
    return projection


def _action_projection(
    *,
    number: str,
    model_call_number: str,
    parsed_result: Any,
    model_step: Mapping[str, Any],
    action_event: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Expose the host-parsed action without inventing a second source record."""
    if action_event is not None:
        raw: Dict[str, Any] = {
            "source": "brain_observations.reasoning.agent_loop.action_decoded",
            "action_decoded": dict(action_event),
        }
    else:
        raw = {"source": "model_step.summary", "model_step": dict(model_step)}
    return {
        "number": number,
        "duration_ms": (
            action_event.get("duration_ms") if action_event is not None else None
        ),
        "status": (
            "failed"
            if action_event is not None and action_event.get("status") == "failed"
            else "parsed"
            if parsed_result is not None
            else "unavailable"
        ),
        "input": {"model_call": model_call_number},
        "output": parsed_result,
        "raw": raw,
    }


def _typed_action_result(payload: Mapping[str, Any]) -> Any:
    """Project the keyed ``action_decoded`` payload into the parsed-action view.

    ``action_type`` maps to the ``type`` key the chain view already renders; a
    decode that produced neither an action nor validation errors renders as
    unavailable rather than as an empty action.
    """
    if not payload:
        return None
    if payload.get("action_type") is None and not payload.get("validation_errors"):
        return None
    result: Dict[str, Any] = {"type": payload.get("action_type")}
    for key in ("query", "recall_reason", "content", "noop_reason"):
        if payload.get(key) is not None:
            result[key] = payload.get(key)
    if payload.get("missing_facts"):
        result["missing_facts"] = list(payload["missing_facts"])
    if payload.get("validation_errors"):
        result["validation_errors"] = list(payload["validation_errors"])
    memory_use_count = payload.get("memory_use_count")
    if isinstance(memory_use_count, int) and memory_use_count > 0:
        result["memory_use_count"] = memory_use_count
    return result


def _observation_record_entry(event: Mapping[str, Any]) -> Dict[str, Any]:
    """Render one keyed ``observation`` envelope as a Run-observation row.

    Only used when the legacy steps array has no row for this iteration: the
    steps rows carry display fields (operation, query, returned evidence)
    the envelope payload does not have.
    """
    payload = _mapping(event.get("payload"))
    return {
        "duration_ms": event.get("duration_ms"),
        "kind": payload.get("observation_kind"),
        "status": payload.get("observation_status"),
        "summary": payload.get("content"),
        "source_ids": list(payload.get("source_ids") or ()),
        "revision": payload.get("revision"),
        "iteration_index": payload.get("iteration_index"),
        "raw": dict(event),
    }


def _judge_entry(event: Mapping[str, Any]) -> Dict[str, Any]:
    """Render one keyed ``judge`` envelope as a completion row."""
    payload = _mapping(event.get("payload"))
    verdict = payload.get("verdict")
    return {
        "duration_ms": event.get("duration_ms"),
        "kind": "judge",
        "status": verdict,
        "summary": payload.get("judge_reason") or verdict,
        "verdict": verdict,
        "action_type": payload.get("action_type"),
        "content": payload.get("content"),
        "judge_reason": payload.get("judge_reason"),
        "revision_requested": payload.get("revision_requested"),
        "external_claim_replaced": payload.get("external_claim_replaced"),
        "current_nest_sanitized": payload.get("current_nest_sanitized"),
        "memory_use_count": payload.get("memory_use_count"),
        "iteration_index": payload.get("iteration_index"),
        "raw": dict(event),
    }


def _observation_stage(
    *,
    number: str,
    observations: Sequence[Mapping[str, Any]],
    duration_ms: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Project an Observations slot only when a real record exists."""
    recorded = [dict(observation) for observation in observations]
    if not recorded:
        return None
    return {
        "number": number,
        "duration_ms": duration_ms,
        "id": "observations",
        "title": "Observations",
        "status": "observed",
        "input": {"step_count": len(recorded)},
        "output": {"records": recorded},
        "evidence_basis": "ReasoningRun.steps",
        "raw": {
            "source": "production_turn_record",
            "steps": recorded,
        },
    }


def _guard_projection(
    *,
    event: Optional[Mapping[str, Any]],
    number: str,
) -> Optional[Dict[str, Any]]:
    """Project the real Guard verdict; never synthesize an empty Guard row."""
    if event is None:
        return None
    payload = _mapping(event.get("payload"))
    outcome = str(payload.get("outcome") or "")
    status = outcome if outcome in {"continued", "stopped"} else "completed"
    decision = (
        "继续" if outcome == "continued" else "停止" if outcome == "stopped" else None
    )
    return {
        "number": number,
        "duration_ms": event.get("duration_ms"),
        "status": status,
        "input": {
            "depth": payload.get("depth"),
            "model_calls_used": payload.get("model_calls_used"),
            "tool_calls_used": payload.get("tool_calls_used"),
        },
        "output": {
            "decision": decision,
            "outcome": payload.get("outcome"),
            "guard": payload.get("guard"),
            "stop_reason": payload.get("stop_reason"),
            "model_calls_remaining": payload.get("model_calls_remaining"),
            "max_model_calls": payload.get("max_model_calls"),
            "max_tool_calls": payload.get("max_tool_calls"),
            "deadline_remaining_ms": payload.get("deadline_remaining_ms"),
            "cancelled": payload.get("cancelled"),
        },
        "raw": dict(event),
    }


def _parsed_model_result(step: Mapping[str, Any]) -> Any:
    """Parse the exact model-step payload without replacing the source record."""
    value = step.get("summary")
    if isinstance(value, Mapping) or isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _decision_stage(
    *,
    decision: Mapping[str, Any],
    reasoning: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
    duration_ms: Optional[float],
) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "plan_id": decision.get("plan_id"),
        "speech_texts": list(_sequence(decision.get("spoken_texts"))),
        "message_texts": list(_sequence(decision.get("message_texts"))),
        "speech_intents": list(_sequence(decision.get("speech_intents"))),
        "message_intents": list(_sequence(decision.get("message_intents"))),
        "motion_intents": list(_sequence(decision.get("motion_intents"))),
        "expression_intents": list(_sequence(decision.get("expression_intents"))),
        "action_intents": list(_sequence(decision.get("action_intents"))),
        "activity_intents": list(_sequence(decision.get("activity_intents"))),
        "noop_intents": list(_sequence(decision.get("noop_intents"))),
    }
    return {
        "number": "5",
        "id": "turn_decision",
        "title": "TurnDecision",
        "status": "completed" if decision else "unavailable",
        "duration_ms": duration_ms,
        "input": {
            "reasoning_status": reasoning.get("status"),
            "model_calls": reasoning.get("model_calls", len(calls)),
            "selected_mode": _mapping(
                _mapping(reasoning.get("decode")).get("report")
            ).get("selected_mode"),
        },
        "output": output,
        "raw": dict(decision),
    }


def _governance_stage(
    *,
    decision: Mapping[str, Any],
    result: Mapping[str, Any],
    receipts: Sequence[Any],
    routing: Optional[Mapping[str, Any]],
    duration_ms: Optional[float],
) -> Dict[str, Any]:
    activity_intents = list(_sequence(decision.get("activity_intents")))
    activity_request = _activity_request_projection(activity_intents)
    delivery = {
        "number": "6.1",
        "id": "delivery",
        "title": "Delivery / Activity request",
        "status": "completed" if result or receipts else "unavailable",
        "input": {
            "message_intents": list(_sequence(decision.get("message_intents"))),
            "speech_intents": list(_sequence(decision.get("speech_intents"))),
            "action_intents": list(_sequence(decision.get("action_intents"))),
            "activity_intents": activity_intents,
        },
        "output": {
            "result": dict(result),
            "receipts": list(receipts),
            "activity_proposals": activity_intents,
        },
        "activity_request": activity_request,
        "raw": {
            "result": dict(result),
            "receipts": list(receipts),
        },
    }
    return {
        "number": "6",
        "id": "governance_delivery",
        "title": "Governance and delivery",
        "status": "completed" if result or receipts else "unavailable",
        "duration_ms": duration_ms,
        "input": {
            "message_intents": list(_sequence(decision.get("message_intents"))),
            "speech_intents": list(_sequence(decision.get("speech_intents"))),
            "action_intents": list(_sequence(decision.get("action_intents"))),
            "activity_intents": activity_intents,
        },
        "output": {
            "result": dict(result),
            "receipts": list(receipts),
            "activity_proposals": activity_intents,
        },
        "routing": dict(routing) if routing is not None else None,
        "raw": {
            "result": dict(result),
            "receipts": list(receipts),
        },
        "delivery": delivery,
    }


def _activity_request_projection(
    activity_intents: Sequence[Any],
) -> Dict[str, Any]:
    """Expose the optional Activity branch without hiding ordinary delivery."""
    requests = list(activity_intents)
    recorded = bool(requests)
    return {
        "id": "activity_request",
        "title": "Activity request",
        "status": "completed" if recorded else "skipped",
        "input": {"activity_intents": requests},
        "output": {"activity_proposals": requests},
        "skip_reason": None if recorded else "no activity request in TurnDecision",
        "evidence_basis": "TurnDecision.activity_intents",
        "raw": {
            "source": "TurnDecision.activity_intents",
            "activity_intents": requests,
        },
    }


def _settlement_stage(
    *,
    turn_id: str,
    result: Mapping[str, Any],
    receipts: Sequence[Any],
    state_after: Mapping[str, Any],
    state_diff: Mapping[str, Any],
    cognitive_turn: Mapping[str, Any],
    memory_writeback: Optional[Mapping[str, Any]],
    emotion_changes: Optional[Mapping[str, Any]],
    energy_settlement: Optional[Mapping[str, Any]],
    duration_ms: float,
    stage_duration_ms: Optional[float],
    warnings: Iterable[Any],
) -> Dict[str, Any]:
    warning_list = list(warnings)
    return {
        "number": "7",
        "id": "settlement",
        "title": "Settlement",
        "status": "completed" if state_after or cognitive_turn else "unavailable",
        "duration_ms": stage_duration_ms,
        "input": {
            "turn_id": turn_id,
            "result": dict(result),
            "receipt_count": len(receipts),
        },
        "output": {
            "recorded_turn_id": turn_id,
            "duration_ms": duration_ms,
            "state_after": dict(state_after),
            "state_diff": dict(state_diff),
            "warnings": warning_list,
            "cognitive_turn": dict(cognitive_turn),
        },
        "memory_writeback": (
            dict(memory_writeback) if memory_writeback is not None else None
        ),
        "emotion_changes": (
            dict(emotion_changes) if emotion_changes is not None else None
        ),
        "energy_settlement": (
            dict(energy_settlement) if energy_settlement is not None else None
        ),
        "raw": {
            "state_after": dict(state_after),
            "state_diff": dict(state_diff),
            "cognitive_turn": dict(cognitive_turn),
            "warnings": warning_list,
        },
    }


def _iteration_groups(steps: Sequence[Mapping[str, Any]]) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    saw_model = False
    for raw_step in steps:
        step = dict(raw_step)
        if str(step.get("kind", "")).lower() == "model":
            if saw_model:
                groups.append(current)
                current = []
            saw_model = True
        current.append(step)
    if current:
        groups.append(current)
    return groups


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()
