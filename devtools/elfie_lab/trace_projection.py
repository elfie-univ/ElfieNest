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
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from elfie.brain.observation import BrainObservation

_MEMORY_BRIDGE_BOUNDARY = "reasoning.memory_bridge"
_CONTEXT_ENGINE_BOUNDARY = "reasoning.context_engine"
_MEMORY_ENCODE_BOUNDARY = "memory.encode"


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
    calls = [_mapping(item) for item in _sequence(stages.get("model_calls"))]
    reasoning = _mapping(stages.get("reasoning"))
    boundary = _mapping(stages.get("turn_boundary"))
    cognitive_turn = _mapping(stages.get("cognitive_turn"))
    typed_input = _mapping(stages.get("typed_input"))
    receipts = list(_sequence(stages.get("output_receipts")))
    first_request = _mapping(calls[0].get("request")) if calls else {}
    frame_id = cognitive_turn.get("frame_id")
    memory = _memory_view(observations, frame_id=frame_id)
    compiles = _turn_compiles(observations, frame_id=frame_id)

    setup = _setup_stage(
        turn_id=turn_id,
        stimulus=stimulus,
        state_before=state_before,
        request=first_request,
        capabilities=_mapping(calls[0].get("capabilities")) if calls else {},
        baseline_memory=memory["baseline_memory"],
    )
    reasoning_stage = _reasoning_stage(
        reasoning=reasoning,
        calls=calls,
        compiles=compiles,
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
            ),
            _context_workspace_stage(
                turn_id=turn_id,
                stimulus=stimulus,
                request=first_request,
                compiles=compiles,
            ),
            setup,
            reasoning_stage,
            _decision_stage(
                decision=decision,
                reasoning=reasoning,
                calls=calls,
            ),
            _governance_stage(
                decision=decision,
                result=result,
                receipts=receipts,
            ),
            _settlement_stage(
                turn_id=turn_id,
                result=result,
                receipts=receipts,
                state_after=state_after,
                state_diff=state_diff,
                cognitive_turn=cognitive_turn,
                duration_ms=duration_ms,
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


def _compile_for_revision(
    compiles: Sequence[BrainObservation],
    context_revision: Any,
) -> Optional[Any]:
    for event in compiles:
        if event.payload.context_revision == context_revision:
            return event.payload
    return None


def _event_admission_stage(
    *,
    turn_id: str,
    stimulus: Mapping[str, Any],
    typed_input: Mapping[str, Any],
    boundary: Mapping[str, Any],
    cognitive_turn: Mapping[str, Any],
) -> Dict[str, Any]:
    source_domain = stimulus.get("source_domain") or typed_input.get("source_domain")
    return {
        "number": "1",
        "id": "event_admission",
        "title": "Event admission",
        "status": "completed" if stimulus or typed_input else "unavailable",
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
) -> Dict[str, Any]:
    first_compile = compiles[0].payload if compiles else None
    output: Dict[str, Any] = {
        "context_revision": request.get("context_revision"),
        "frame_id": request.get("frame_id"),
    }
    if first_compile is not None:
        output["compiled"] = _compiled_summary(first_compile)
    return {
        "number": "2",
        "id": "context_workspace",
        "title": "Context Workspace",
        "status": "completed" if request or compiles else "unavailable",
        "input": {
            "turn_id": turn_id,
            "message": stimulus.get("message", ""),
        },
        "output": output,
        "raw": {
            "source": "ModelGenerationRequest.user_prompt",
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
    capabilities: Mapping[str, Any],
    baseline_memory: Mapping[str, Any],
) -> Dict[str, Any]:
    response_schema = _mapping(request.get("response_schema"))
    setup_output = {
        "turn_id": turn_id,
        "source_domain": request.get("source_domain") or stimulus.get("source_domain"),
        "context_revision": request.get("context_revision"),
        "capability_revision": request.get("capability_revision"),
        "deadline": request.get("deadline"),
        "reasoning_mode": request.get("reasoning_mode"),
        "response_mode": request.get("response_mode"),
        "response_schema": response_schema.get("name"),
        "temperature": request.get("temperature"),
        "max_tokens": request.get("max_tokens"),
        "allowed_tools": list(_sequence(request.get("allowed_tools"))),
        "tool_definition_count": len(_sequence(request.get("tool_definitions"))),
        "skill_count": len(_sequence(request.get("available_skills"))),
        "capabilities": capabilities,
    }
    return {
        "number": "3",
        "id": "setup",
        "title": "Setup",
        "status": "completed" if state_before or request else "unavailable",
        "input": {
            "turn_id": turn_id,
            "source_domain": stimulus.get("source_domain"),
        },
        "output": setup_output,
        "owner_snapshots": _owner_snapshots(
            state_before,
            captured_at=request.get("created_at"),
        ),
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
    calls: Sequence[Mapping[str, Any]],
    compiles: Sequence[BrainObservation],
) -> Dict[str, Any]:
    steps = [_mapping(step) for step in _sequence(reasoning.get("steps"))]
    groups = _iteration_groups(steps)
    iterations: List[Dict[str, Any]] = []
    iteration_count = max(len(calls), len(groups))
    for index in range(iteration_count):
        call = calls[index] if index < len(calls) else {}
        request = _mapping(call.get("request"))
        group = groups[index] if index < len(groups) else []
        model_step = next(
            (step for step in group if str(step.get("kind", "")).lower() == "model"),
            {},
        )
        observations = [
            step
            for step in group
            if str(step.get("kind", "")).lower() not in {"model", "verify"}
        ]
        completions = [
            step for step in group if str(step.get("kind", "")).lower() == "verify"
        ]
        iteration_number = f"4.{index + 1}"
        model_call_number = f"{iteration_number}.2"
        compile_payload = _compile_for_revision(
            compiles,
            request.get("context_revision"),
        )
        observation_stage = _observation_stage(
            number=f"{iteration_number}.4",
            observations=observations,
        )
        iterations.append(
            {
                "number": iteration_number,
                "status": (
                    "failed"
                    if call.get("error")
                    else "completed"
                    if call
                    else "unavailable"
                ),
                "input": {
                    "context_revision": request.get("context_revision"),
                    "frame_id": request.get("frame_id"),
                },
                "context_build": {
                    "number": f"{iteration_number}.1",
                    "status": (
                        "completed" if request or compile_payload else "unavailable"
                    ),
                    "input": {
                        "context_revision": request.get("context_revision"),
                    },
                    "output": {
                        "context_revision": request.get("context_revision"),
                        "compiled": (
                            _compiled_summary(compile_payload)
                            if compile_payload is not None
                            else None
                        ),
                    },
                    "raw": {
                        "context_revision": request.get("context_revision"),
                        "system_prompt": request.get("system_prompt"),
                        "user_prompt": request.get("user_prompt"),
                    },
                },
                "model_call": _model_call_projection(
                    call,
                    number=model_call_number,
                    model_step=model_step,
                    parsed_result=_parsed_model_result(model_step),
                ),
                "action": _action_projection(
                    number=f"{iteration_number}.3",
                    model_call_number=model_call_number,
                    model_step=model_step,
                    parsed_result=_parsed_model_result(model_step),
                ),
                "observations": [dict(step) for step in observations],
                "observation_stage": observation_stage,
                "completion": completions,
                "guard": _guard_projection(
                    number=(f"{iteration_number}.{5 + len(completions)}"),
                ),
                "raw": {
                    "steps": group,
                    "model_call": dict(call) if call else None,
                    "source": "production_turn_record",
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
    return {
        "number": "4",
        "id": "reasoning_run",
        "title": "ReasoningRun",
        "status": reasoning.get("status", "unavailable"),
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
        "raw": dict(reasoning),
    }


def _model_call_projection(
    call: Mapping[str, Any],
    *,
    number: str,
    model_step: Mapping[str, Any],
    parsed_result: Any,
) -> Dict[str, Any]:
    request = _mapping(call.get("request"))
    response = call.get("response")
    result = call.get("result")
    projection: Dict[str, Any] = {
        "number": number,
        "status": (
            "failed" if call.get("error") else "completed" if call else "unavailable"
        ),
        "input": {
            "system_prompt": request.get("system_prompt"),
            "user_prompt": request.get("user_prompt"),
        },
        "output": {
            "response": response,
            "parsed_result": parsed_result,
            "provider": call.get("provider"),
            "model": call.get("model"),
            "selected_mode": _mapping(result).get("selected_mode")
            if isinstance(result, Mapping)
            else None,
        },
        "effective_parameters": call.get("effective_parameters"),
        "capabilities": call.get("capabilities"),
        "duration_ms": call.get("duration_ms"),
        "response": response,
        "result": result,
        "reasoning_step": model_step,
        "raw": dict(call),
    }
    provider_raw = call.get("provider_raw")
    if provider_raw not in (None, "", {}, []):
        projection["provider_raw"] = provider_raw
    return projection


def _action_projection(
    *,
    number: str,
    model_call_number: str,
    model_step: Mapping[str, Any],
    parsed_result: Any,
) -> Dict[str, Any]:
    """Expose the host-parsed action without inventing a second source record."""
    return {
        "number": number,
        "status": "recorded" if parsed_result is not None else "unavailable",
        "input": {"model_call": model_call_number},
        "output": parsed_result,
        "raw": {
            "source": "model_step.summary",
            "model_step": dict(model_step),
        },
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
    duration_ms: float,
    warnings: Iterable[Any],
) -> Dict[str, Any]:
    warning_list = list(warnings)
    return {
        "number": "7",
        "id": "settlement",
        "title": "Settlement",
        "status": "completed" if state_after or cognitive_turn else "unavailable",
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
