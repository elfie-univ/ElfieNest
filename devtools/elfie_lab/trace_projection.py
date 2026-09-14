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
) -> Optional[float]:
    """Sum the measured ``duration_ms`` of one stage's member envelopes.

    Read-only over the envelopes the Brain already recorded: no duration
    is re-measured or inferred.  A member event without a measured
    duration contributes zero, and a stage with no member events at all
    reports ``None`` so the frontend renders the honest "未记录".
    """
    member_durations = [
        event.duration_ms
        for event in observations
        if any(
            event.boundary == boundary and event.kind in kinds
            for boundary, kinds in boundaries_and_kinds
        )
    ]
    if not member_durations:
        return None
    return float(sum(value for value in member_durations if value is not None))


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
    return _scoped_events(
        observations,
        boundary=_CONTEXT_ENGINE_BOUNDARY,
        kinds=("context_trimmed",),
        frame_id=frame_id,
    )


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
        "summaries": [
            {
                "summary_id": item.summary_id,
                "version": item.version,
                "unresolved_count": item.unresolved_count,
            }
            for item in payload.summaries
        ],
    }


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
        "max_tool_calls": payload.max_tool_calls,
        "deadline_seconds": payload.deadline_seconds,
        "absolute_deadline": _iso_utc(payload.absolute_deadline),
        "max_context_tokens": payload.max_context_tokens,
        "cognitive_mode": payload.cognitive_mode,
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
    first_request = _model_request_view(model_calls[0]) if model_calls else {}
    stage_durations = {
        stage_id: _stage_duration(observations, members)
        for stage_id, members in _STAGE_EVENT_MEMBERS.items()
    }

    setup = _setup_stage(
        turn_id=turn_id,
        stimulus=stimulus,
        state_before=state_before,
        request=first_request,
        baseline_memory=memory["baseline_memory"],
        mode_selection=_mode_selection_block(observations, frame_id=frame_id),
        budget=_budget_block(observations, frame_id=frame_id),
        selfhood_projection=_selfhood_projection_block(observations, frame_id=frame_id),
        duration_ms=stage_durations["setup"],
    )
    reasoning_stage = _reasoning_stage(
        reasoning=reasoning,
        loop_events=_turn_agent_loop_events(observations, frame_id=frame_id),
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
                appended=_appended_block(observations, frame_id=frame_id),
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
        scoped = [event for event in compiles if event.frame_id == frame_id]
        if scoped:
            compiles = scoped
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
        scoped = [event for event in events if str(event.frame_id) == str(frame_id)]
        if scoped:
            events = scoped
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
        scoped = [event for event in events if str(event.frame_id) == str(frame_id)]
        if scoped:
            events = scoped
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
        "temperature": payload.get("temperature"),
        "max_tokens": payload.get("max_tokens"),
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


def _compiled_conversation_rows(payload: Any) -> List[Dict[str, Any]]:
    """Project the compiled conversation rows carried by the payload.

    Rows come from the ``compiled_context`` envelope payload's raw
    ``conversation`` tuples — the exact prior-turn rows the Context Engine
    kept — never from parsing prompt text.  ``display_name`` falls back to
    ``actor_id`` only as the read-side speaker label.
    """
    rows: List[Dict[str, Any]] = []
    for row in getattr(payload, "conversation", ()) or ():
        display_name = getattr(row, "display_name", None)
        rows.append(
            {
                "speaker": display_name or getattr(row, "actor_id", ""),
                "content": row.content,
                "occurred_at": _iso_utc(row.occurred_at),
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
    return {
        "number": "1",
        "id": "event_admission",
        "title": "Event admission",
        "status": "completed" if stimulus or typed_input else "unavailable",
        "duration_ms": duration_ms,
        "input": {
            "source_domain": source_domain,
            "message": stimulus.get("message", ""),
            "modalities": list(_sequence(typed_input.get("modalities"))),
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
        output["conversation"] = _compiled_conversation_rows(first_compile)
        # Run-observation content exists only as payload counts: these keys
        # stay null rather than being reconstructed from prompt text (P1).
        output["current_observations"] = None
        output["current_run_observations"] = None
    return {
        "number": "2",
        "id": "context_workspace",
        "title": "Context Workspace",
        "status": "completed" if request or compiles else "unavailable",
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
    }
    return {
        "number": "3",
        "id": "setup",
        "title": "Setup",
        "status": "completed" if state_before or request else "unavailable",
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
        "owner_snapshots": _owner_snapshots(state_before),
        "baseline_memory": baseline_memory,
        "raw": {
            "state_before": dict(state_before),
            "request": dict(request),
        },
    }


def _owner_snapshots(
    state: Mapping[str, Any],
    *,
    captured_at: Any = None,
) -> List[Dict[str, Any]]:
    emotion = {
        "emotions": state.get("emotions"),
        "primary_emotion": state.get("primary_emotion"),
        "emotion_revision": state.get("emotion_revision"),
    }
    energy_keys = (
        "energy",
        "fatigue",
        "is_sleeping",
        "cognitive_mode",
        "normal_budget_available",
        "emergency_reserve_available",
        "reserved_cognitive_budget",
        "energy_revision",
    )
    energy = {key: state.get(key) for key in energy_keys if key in state}
    values = (
        ("orientation", "Orientation", state.get("orientation")),
        ("selfhood", "Selfhood", state.get("selfhood")),
        ("emotion", "Emotion", emotion),
        ("energy", "Energy", energy),
        ("motivation", "Motivation", state.get("motivation")),
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
                    "source_record": "state_before",
                    "captured_at": captured_at,
                },
                "output": value,
                "raw": value,
                "evidence_basis": "state_before",
            }
        )
    return snapshots


def _reasoning_stage(
    *,
    reasoning: Mapping[str, Any],
    loop_events: Sequence[Mapping[str, Any]],
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
        key for key, bucket in buckets.items() if bucket.get("model_call")
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
        observations = steps_observations or typed_observations
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
        context_output: Dict[str, Any] = {
            "context_revision": payload.get("context_revision"),
            "compiled": (
                _compiled_summary(compile_payload)
                if compile_payload is not None
                else None
            ),
        }
        if compile_payload is not None:
            context_output["conversation"] = _compiled_conversation_rows(
                compile_payload
            )
            context_output["prompt_sections"] = _compiled_sections(compile_payload)
        if compile_index is not None and compile_index < len(trims):
            context_output["trim"] = _trim_view(trims[compile_index].payload)
        observation_stage = _observation_stage(
            number=f"{iteration_number}.4",
            observations=observations,
        )
        # The ModelCall card keeps the wire-format parse the session chain pins;
        # the Cognitive Action card prefers the keyed envelope decode.
        model_call_parsed = steps_result if steps_result is not None else typed_result
        action_parsed = typed_result if typed_result is not None else steps_result
        guard_number = f"{iteration_number}.{5 + len(completions)}"
        iterations.append(
            {
                "number": iteration_number,
                "status": (
                    "failed"
                    if call and str(call.get("status")) == "failed"
                    else "completed"
                    if call
                    else "unavailable"
                ),
                "input": {
                    "context_revision": payload.get("context_revision"),
                    "frame_id": call.get("frame_id"),
                },
                "context_build": {
                    "number": f"{iteration_number}.1",
                    "status": (
                        "completed" if payload or compile_payload else "unavailable"
                    ),
                    "input": {
                        "context_revision": payload.get("context_revision"),
                    },
                    "output": context_output,
                    "raw": {
                        "context_revision": payload.get("context_revision"),
                        "system_prompt": payload.get("system_prompt"),
                        "user_prompt": payload.get("user_prompt"),
                    },
                },
                "model_call": _model_call_projection(
                    call,
                    number=model_call_number,
                    model_step=model_step,
                    parsed_result=model_call_parsed,
                ),
                "action": _action_projection(
                    number=f"{iteration_number}.3",
                    model_call_number=model_call_number,
                    parsed_result=action_parsed,
                    model_step=model_step,
                    action_event=action_event,
                ),
                "observations": [dict(step) for step in observations],
                "observation_stage": observation_stage,
                "completion": completions,
                "guard": _guard_projection(
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
        )

    report = _mapping(_mapping(reasoning.get("decode")).get("report"))
    reasoning_raw = dict(reasoning)
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
        },
        "raw": reasoning_raw,
    }


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
    projection: Dict[str, Any] = {
        "number": number,
        "status": "failed" if failed else "completed",
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
            "temperature": payload.get("temperature"),
            "max_tokens": payload.get("max_tokens"),
            "context_revision": payload.get("context_revision"),
            "capability_revision": payload.get("capability_revision"),
        },
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
        "status": "recorded" if parsed_result is not None else "unavailable",
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
    return result


def _observation_record_entry(event: Mapping[str, Any]) -> Dict[str, Any]:
    """Render one keyed ``observation`` envelope as a Run-observation row.

    Only used when the legacy steps array has no row for this iteration: the
    steps rows carry display fields (operation, query, returned evidence)
    the envelope payload does not have.
    """
    payload = _mapping(event.get("payload"))
    return {
        "kind": payload.get("observation_kind"),
        "status": payload.get("observation_status"),
        "summary": payload.get("content"),
        "source_ids": list(payload.get("source_ids") or ()),
        "revision": payload.get("revision"),
        "iteration_index": payload.get("iteration_index"),
    }


def _judge_entry(event: Mapping[str, Any]) -> Dict[str, Any]:
    """Render one keyed ``judge`` envelope as a completion row."""
    payload = _mapping(event.get("payload"))
    verdict = payload.get("verdict")
    return {
        "kind": "judge",
        "status": verdict,
        "summary": payload.get("judge_reason") or verdict,
        "verdict": verdict,
        "action_type": payload.get("action_type"),
        "revision_requested": payload.get("revision_requested"),
        "iteration_index": payload.get("iteration_index"),
    }


def _observation_stage(
    *,
    number: str,
    observations: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Keep the fixed Observations slot visible, including when it is empty."""
    recorded = [dict(observation) for observation in observations]
    has_observations = bool(recorded)
    return {
        "number": number,
        "id": "observations",
        "title": "Observations",
        "status": "recorded" if has_observations else "skipped",
        "input": {"step_count": len(recorded)},
        "output": {"records": recorded} if has_observations else {},
        "skip_reason": (
            None
            if has_observations
            else "no observation/tool/skill record in this iteration"
        ),
        "evidence_basis": "ReasoningRun.steps",
        "raw": {
            "source": "production_turn_record",
            "steps": recorded,
        },
    }


def _guard_projection(
    *,
    number: str,
) -> Dict[str, Any]:
    """Keep the fixed Guard slot honest when no Guard event was persisted."""
    return {
        "number": number,
        "status": "skipped",
        "input": {},
        "output": {},
        "skip_reason": "separate Guard record is not persisted",
        "evidence_basis": "ReasoningRun.status + ordered steps",
        "raw": {
            "source": "production_turn_record",
            "available": False,
            "reason": "separate Guard record is not persisted",
        },
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
        "status": "recorded" if recorded else "skipped",
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
