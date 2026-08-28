"""Project Elfie Lab's real typed turn evidence into evaluation artifacts."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from devtools.brain_eval.contracts import (
    EffectEvidence,
    EffectStatus,
    EpisodeEvidence,
    ExternalDomain,
    ModelExecutionEvidence,
    ResourceObservation,
    SourceDomain,
    TurnEvidence,
)


def episode_from_lab_turn_records(
    *,
    candidate_id: str,
    candidate_spec_sha256: str,
    scenario_family_id: str,
    scenario_version: str,
    variant_id: str,
    fixture_id: str,
    seed: int,
    hidden: bool,
    records: Iterable[Mapping[str, Any]],
) -> EpisodeEvidence:
    """Use decisions, scopes and receipts; never infer truth from generated prose."""

    selected = tuple(records)
    turns: List[TurnEvidence] = []
    effects: List[EffectEvidence] = []
    public_outputs: List[str] = []
    for record in selected:
        turn, turn_effects, outputs = _project_turn(record)
        turns.append(turn)
        effects.extend(turn_effects)
        public_outputs.extend(outputs)

    output_tokens = _sum_optional_ints(
        tuple(
            _optional_int(record.get("model_call"), "output_tokens")
            for record in selected
        )
    )
    input_tokens = _sum_optional_ints(
        tuple(
            _optional_int(record.get("model_call"), "input_tokens")
            for record in selected
        )
    )
    costs = _sum_optional_ints(
        tuple(
            _optional_int(record.get("model_call"), "cost_microunits")
            for record in selected
        )
    )
    model_executions = tuple(
        _model_execution(record.get("model_call"))
        for record in selected
        if _mapping(record.get("model_call"))
    )
    return EpisodeEvidence(
        candidate_id=candidate_id,
        candidate_spec_sha256=candidate_spec_sha256,
        scenario_family_id=scenario_family_id,
        scenario_version=scenario_version,
        variant_id=variant_id,
        fixture_id=fixture_id,
        seed=seed,
        execution_success=bool(selected)
        and all(
            bool(_mapping(record.get("result")).get("success")) for record in selected
        ),
        hidden=hidden,
        turns=tuple(turns),
        effects=tuple(effects),
        public_outputs=tuple(public_outputs),
        model_executions=model_executions,
        resources=ResourceObservation(
            latency_ms=sum(
                float(record.get("duration_ms", 0.0)) for record in selected
            ),
            model_calls=sum(
                1
                for record in selected
                if not bool(_mapping(record.get("model_call")).get("skipped"))
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microunits=costs,
        ),
    )


def _project_turn(
    record: Mapping[str, Any],
) -> tuple[TurnEvidence, tuple[EffectEvidence, ...], tuple[str, ...]]:
    trace = _mapping(record.get("trace"))
    stages = _mapping(trace.get("stages"))
    boundary = _mapping(stages.get("turn_boundary"))
    stimulus = _mapping(record.get("stimulus_bundle"))
    source_domain = SourceDomain(
        str(boundary.get("source_domain") or stimulus.get("source_domain"))
    )
    interaction_scope = _mapping(boundary.get("interaction_scope"))
    source_scope_id = _source_scope_id(source_domain, interaction_scope)
    decision = _mapping(record.get("decision"))
    receipts = {
        str(receipt.get("intent_id")): receipt
        for receipt in _mapping_sequence(stages.get("output_receipts"))
    }
    domains: List[ExternalDomain] = []
    scope_ids: List[str] = []
    effects: List[EffectEvidence] = []
    for collection_name, domain in (
        ("message_intents", ExternalDomain.COMMUNICATION),
        ("speech_intents", ExternalDomain.EMBODIED),
        ("motion_intents", ExternalDomain.EMBODIED),
        ("expression_intents", ExternalDomain.EMBODIED),
    ):
        for intent in _mapping_sequence(decision.get(collection_name)):
            intent_id = str(intent.get("intent_id"))
            receipt = receipts.get(intent_id, {})
            domains.append(domain)
            scope_ids.append(
                str(
                    intent.get("conversation_id")
                    or interaction_scope.get("conversation_id")
                    or interaction_scope.get("body_id")
                    or source_scope_id
                    or "unknown-scope"
                )
            )
            effects.append(
                EffectEvidence(
                    effect_id=intent_id,
                    domain=domain,
                    status=_effect_status(
                        str(receipt.get("status") or intent.get("status") or "pending")
                    ),
                    receipt_id=(
                        str(receipt["receipt_id"])
                        if receipt.get("receipt_id") is not None
                        else None
                    ),
                    irreversible=collection_name != "expression_intents",
                    authorized=True,
                    trigger_kind="online_turn",
                )
            )
    outputs = tuple(
        str(text)
        for key in ("message_texts", "spoken_texts")
        for text in _sequence(decision.get(key))
        if str(text).strip()
    )
    return (
        TurnEvidence(
            turn_id=str(record.get("turn_id")),
            source_domain=source_domain,
            source_scope_id=source_scope_id,
            output_domains=tuple(domains),
            output_scope_ids=tuple(scope_ids),
        ),
        tuple(effects),
        outputs,
    )


def _source_scope_id(
    domain: SourceDomain,
    interaction_scope: Mapping[str, Any],
) -> Optional[str]:
    if domain is SourceDomain.COMMUNICATION:
        value = interaction_scope.get("conversation_id")
    elif domain is SourceDomain.EMBODIED:
        value = interaction_scope.get("body_id")
    else:
        value = interaction_scope.get("trigger_id")
    return str(value) if value is not None else None


def _effect_status(value: str) -> EffectStatus:
    if value == "completed":
        return EffectStatus.COMPLETED
    if value == "cancelled":
        return EffectStatus.CANCELLED
    if value in {"failed", "rejected", "interrupted", "timed_out"}:
        return EffectStatus.FAILED
    return EffectStatus.PENDING


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _mapping_sequence(value: Any) -> Tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


def _optional_int(value: Any, key: str) -> Optional[int]:
    raw = _mapping(value).get(key)
    return int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else None


def _model_execution(value: Any) -> ModelExecutionEvidence:
    payload = _mapping(value)
    skipped = bool(payload.get("skipped"))
    provider = payload.get("provider")
    model = payload.get("model")
    error = payload.get("error")
    return ModelExecutionEvidence(
        food_key=str(payload.get("food_key") or "unknown"),
        provider=str(provider) if provider is not None else None,
        model_id=str(model) if model is not None else None,
        skipped=skipped,
        degraded=bool(payload.get("degraded")),
        error=str(error) if error is not None else None,
    )


def _sum_optional_ints(values: Tuple[Optional[int], ...]) -> Optional[int]:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


__all__ = ("episode_from_lab_turn_records",)
