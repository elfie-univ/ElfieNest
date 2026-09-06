"""Project the production Brain Turn into a compact, provenance-preserving trace.

This module is deliberately a read-only projection.  The Brain remains the
owner of execution facts; the Lab only groups the records that already exist
on a ``TurnRecord`` so that one Turn can be inspected as one causal chain.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


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
    baseline_memory = _memory_status(first_request.get("user_prompt"))
    memory_observations = _memory_observations(reasoning.get("steps"))
    relevant_memory = _prompt_section(
        first_request.get("user_prompt"),
        "RELEVANT_MEMORY",
    )
    memory_points = _memory_evidence_points(relevant_memory)
    selected_memory = _sequence(_mapping(decision).get("memory_uses"))

    setup = _setup_stage(
        turn_id=turn_id,
        stimulus=stimulus,
        state_before=state_before,
        request=first_request,
        capabilities=_mapping(calls[0].get("capabilities")) if calls else {},
        relevant_memory=relevant_memory,
        memory_points=memory_points,
    )
    reasoning_stage = _reasoning_stage(
        reasoning=reasoning,
        calls=calls,
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
        "memory": {
            "status": baseline_memory.get("status", "unavailable"),
            "query": baseline_memory.get("query", ""),
            "revision": baseline_memory.get("revision"),
            "reason": baseline_memory.get("reason"),
            "returned_evidence": relevant_memory,
            "returned_points": memory_points,
            "selected": selected_memory,
            "on_demand": memory_observations,
            "raw": {
                "baseline": baseline_memory,
                "relevant_memory": relevant_memory,
                "on_demand": memory_observations,
            },
        },
    }


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
) -> Dict[str, Any]:
    user_prompt = request.get("user_prompt")
    context_only = _prompt_section(user_prompt, "CONTEXT_ONLY")
    current_observations = _prompt_section(user_prompt, "CURRENT_OBSERVATIONS")
    current_run_observations = _prompt_section(
        user_prompt,
        "CURRENT_RUN_OBSERVATIONS",
    )
    sections = [
        name
        for name, value in (
            ("CONTEXT_ONLY", context_only),
            ("CURRENT_OBSERVATIONS", current_observations),
            ("CURRENT_RUN_OBSERVATIONS", current_run_observations),
        )
        if value
    ]
    has_request = bool(request)
    return {
        "number": "2",
        "id": "context_workspace",
        "title": "Context Workspace",
        "status": "completed" if has_request else "unavailable",
        "input": {
            "turn_id": turn_id,
            "message": stimulus.get("message", ""),
        },
        "output": {
            "context_revision": request.get("context_revision"),
            "frame_id": request.get("frame_id"),
            "prompt_sections": sections,
            "conversation": context_only,
            "current_observations": current_observations,
            "current_run_observations": current_run_observations,
        },
        "raw": {
            "source": "ModelGenerationRequest.user_prompt",
            "context_revision": request.get("context_revision"),
            "user_prompt": user_prompt,
        },
    }


def _setup_stage(
    *,
    turn_id: str,
    stimulus: Mapping[str, Any],
    state_before: Mapping[str, Any],
    request: Mapping[str, Any],
    capabilities: Mapping[str, Any],
    relevant_memory: str,
    memory_points: Sequence[Mapping[str, Any]],
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
    baseline_memory = _memory_status(request.get("user_prompt"))
    baseline_memory["returned_evidence"] = relevant_memory
    baseline_memory["returned_points"] = list(memory_points)
    baseline_memory["evidence_basis"] = "model_request.RELEVANT_MEMORY"
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
                    "observations_before_call": _prompt_section(
                        request.get("user_prompt"),
                        "CURRENT_RUN_OBSERVATIONS",
                    ),
                },
                "context_build": {
                    "number": f"{iteration_number}.1",
                    "status": "completed" if request else "unavailable",
                    "input": {
                        "context_revision": request.get("context_revision"),
                        "run_observations": _prompt_section(
                            request.get("user_prompt"),
                            "CURRENT_RUN_OBSERVATIONS",
                        ),
                    },
                    "output": {
                        "context_revision": request.get("context_revision"),
                        "prompt_sections": _request_prompt_sections(request),
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
                "observations": [
                    _observation_projection(step) for step in observations
                ],
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


def _memory_observations(value: Any) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []
    for raw_step in _sequence(value):
        step = _mapping(raw_step)
        if step.get("operation") != "memory_recall":
            continue
        summary = str(step.get("summary", ""))
        match = re.match(
            r"query=(.*?); reason=(.*?); result=(.*?); detail=(.*)$",
            summary,
            flags=re.DOTALL,
        )
        observations.append(
            {
                "status": step.get("status"),
                "query": match.group(1) if match else None,
                "reason": match.group(2) if match else None,
                "returned_evidence": match.group(3) if match else summary,
                "detail": match.group(4) if match else None,
                "raw": step,
            }
        )
    return observations


def _observation_projection(step: Mapping[str, Any]) -> Dict[str, Any]:
    """Add parsed fields to a memory observation while retaining its raw step."""
    if step.get("operation") != "memory_recall":
        return dict(step)
    parsed = _memory_observation_from_step(step)
    return {**dict(step), **parsed}


def _memory_observation_from_step(step: Mapping[str, Any]) -> Dict[str, Any]:
    summary = str(step.get("summary", ""))
    match = re.match(
        r"query=(.*?); reason=(.*?); result=(.*?); detail=(.*)$",
        summary,
        flags=re.DOTALL,
    )
    return {
        "query": match.group(1) if match else None,
        "reason": match.group(2) if match else None,
        "returned_evidence": match.group(3) if match else summary,
        "detail": match.group(4) if match else None,
    }


def _memory_evidence_points(value: Any) -> List[Dict[str, Any]]:
    """Extract readable evidence points while retaining the full block as Raw."""
    if not isinstance(value, str) or not value.strip():
        return []
    points: List[Dict[str, Any]] = []
    for match in re.finditer(
        r"<(FACT|NODE|EPISODE)\b[^>]*>(.*?)</\1>",
        value,
        flags=re.DOTALL,
    ):
        kind, body = match.groups()
        status = _memory_line(body, "状态")
        points.append(
            {
                "kind": kind.lower(),
                "claim": _memory_line(body, "事实") or _memory_line(body, "内容"),
                "relation": _memory_line(body, "关系"),
                "evidence": _memory_evidence_line(body),
                "status": status.split("；", 1)[0] if status else None,
                "confidence": _memory_confidence(body),
            }
        )
    return points


def _memory_line(body: str, label: str) -> Optional[str]:
    match = re.search(rf"^{re.escape(label)}：(.+)$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _memory_evidence_line(body: str) -> Optional[str]:
    match = re.search(r"^证据原文[^：]*：(.+)$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _memory_confidence(body: str) -> Optional[float]:
    match = re.search(r"置信度：([0-9]+(?:\.[0-9]+)?)", body)
    return float(match.group(1)) if match else None


def _memory_status(value: Any) -> Dict[str, Any]:
    prompt = value if isinstance(value, str) else ""
    match = re.search(
        r"MEMORY_RECALL_STATUS:\n"
        r"status=(?P<status>[^;\n]+);\s*"
        r"revision=(?P<revision>[^;\n]+);\s*"
        r"reason=(?P<reason>[^\n]+)",
        prompt,
    )
    if match is None:
        return {"status": "unavailable", "query": "", "revision": None, "reason": None}
    raw_revision = match.group("revision").strip()
    try:
        revision: Any = int(raw_revision)
    except ValueError:
        revision = raw_revision
    return {
        "status": match.group("status").strip(),
        "query": _prompt_section(prompt, "CURRENT_MESSAGE"),
        "revision": revision,
        "reason": match.group("reason").strip(),
    }


def _prompt_section(value: Any, name: str) -> str:
    prompt = value if isinstance(value, str) else ""
    marker = f"{name}:\n"
    start = prompt.find(marker)
    if start < 0:
        return ""
    content_start = start + len(marker)
    end = len(prompt)
    for candidate in (
        "TRUSTED_EXECUTION_CONTEXT",
        "MEMORY_RECALL_STATUS",
        "RELEVANT_MEMORY",
        "CONTEXT_SUMMARIES",
        "ACTIVE_ACTIVITIES",
        "CURRENT_OBSERVATIONS",
        "CONTEXT_ONLY",
        "CURRENT_RUN_OBSERVATIONS",
        "CURRENT_MESSAGE",
    ):
        if candidate == name:
            continue
        candidate_start = prompt.find(f"\n\n{candidate}:\n", content_start)
        if candidate_start >= 0:
            end = min(end, candidate_start)
    return prompt[content_start:end].strip()


def _request_prompt_sections(request: Mapping[str, Any]) -> List[str]:
    user_prompt = request.get("user_prompt")
    names = (
        "TRUSTED_EXECUTION_CONTEXT",
        "MEMORY_RECALL_STATUS",
        "RELEVANT_MEMORY",
        "CONTEXT_SUMMARIES",
        "ACTIVE_ACTIVITIES",
        "CURRENT_OBSERVATIONS",
        "CONTEXT_ONLY",
        "CURRENT_RUN_OBSERVATIONS",
        "CURRENT_MESSAGE",
    )
    return [name for name in names if _prompt_section(user_prompt, name)]


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()
