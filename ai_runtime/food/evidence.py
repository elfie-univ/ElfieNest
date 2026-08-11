"""Read-only model evidence derived from Provider inventory and SQLite reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from ai_runtime.food.planner import EVIDENCE_MAX_AGE, ModelEvidence
from infrastructure.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from infrastructure.models.providers.profiles import get_product
from infrastructure.persistence.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from infrastructure.persistence.report_repository import (
    ReportRepository,
    ValidationObservation,
)


def query_model_evidence(
    *,
    repository: Optional[ReportRepository] = None,
    connection_store: Optional[ProviderConnectionStore] = None,
    connections: Optional[Mapping[str, ProviderConnection]] = None,
    observations: Optional[Sequence[ValidationObservation]] = None,
    now: Optional[datetime] = None,
) -> dict[str, ModelEvidence]:
    """Project endpoint models and their latest immutable validation facts."""
    latest = observations
    if latest is None:
        latest = (repository or ReportRepository()).current(subject_kind="model")
    by_subject = {
        item.subject_id: item for item in latest if item.subject_kind == "model"
    }
    current = now or datetime.now(timezone.utc)
    result: dict[str, ModelEvidence] = {}
    inventory = (
        connections
        if connections is not None
        else (connection_store or ProviderConnectionStore()).load().connections
    )
    for connection in inventory.values():
        if not connection.enabled or connection.archived:
            continue
        profile = get_product(connection.catalog_id)
        is_local = bool(profile and profile.connection_method == "local")
        for model in connection.models:
            subject_id = f"{connection.connection_id}/{model.endpoint_model_id}"
            result[subject_id] = _project_model(
                subject_id,
                model,
                by_subject.get(subject_id),
                is_local=is_local,
                now=current,
            )
    return result


def record_model_evidence(
    evidence: Sequence[ModelEvidence],
    *,
    repository: Optional[ReportRepository] = None,
    scope: str,
    trigger: str,
) -> Optional[str]:
    """Append validation results through the report repository's only writer API."""
    if not evidence:
        return None
    report_repository = repository or ReportRepository()
    run_id = report_repository.start_run(scope=scope, trigger=trigger)
    for item in evidence:
        report_repository.append_observation(
            run_id=run_id,
            subject_kind="model",
            subject_id=item.model,
            observed_at=item.observed_at or None,
            status="passed" if item.verified else "failed",
            latency_ms=item.latency_ms,
            details={
                "capabilities": sorted(item.capabilities),
                "cost_grade": item.cost_grade,
                "tool_test_passed": item.tool_test_passed,
            },
        )
    report_repository.finish_run(run_id, status="complete")
    return run_id


def _project_model(
    subject_id: str,
    model: ProviderModelRecord,
    observation: Optional[ValidationObservation],
    *,
    is_local: bool,
    now: datetime,
) -> ModelEvidence:
    state = _validation_state(model, observation, now)
    details: Mapping[str, Any] = observation.details if observation else {}
    raw_capabilities = details.get("capabilities", ())
    observed_capabilities = (
        frozenset(str(item) for item in raw_capabilities)
        if isinstance(raw_capabilities, (list, tuple, set))
        else frozenset()
    )
    capabilities = observed_capabilities | known_capabilities(
        model.endpoint_model_id,
        model.display_name,
    )
    if model.supports_tools:
        capabilities |= {"tools"}
    if model.supports_vision:
        capabilities |= {"vision"}
    if model.supports_reasoning:
        capabilities |= {"reasoning"}
    return ModelEvidence(
        model=subject_id,
        display_name=canonical_display_name(subject_id, model.display_name),
        capabilities=capabilities or frozenset({"text"}),
        verified=state == "verified",
        cost_grade=_int_value(details, "cost_grade", 2),
        latency_ms=observation.latency_ms if observation else None,
        tool_test_passed=bool(details.get("tool_test_passed", False)),
        local=is_local,
        observed_at=observation.observed_at if observation else "",
        status=state,
    )


def _validation_state(
    model: ProviderModelRecord,
    observation: Optional[ValidationObservation],
    now: datetime,
) -> str:
    if model.hidden:
        return "hidden"
    if model.retired:
        return "retired"
    if not model.available:
        return "unavailable"
    if observation is None:
        return "never_verified"
    if observation.status != "passed":
        return "failed"
    try:
        observed = datetime.fromisoformat(
            observation.observed_at.replace("Z", "+00:00")
        )
    except ValueError:
        return "stale"
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return "verified" if now - observed <= EVIDENCE_MAX_AGE else "stale"


def _int_value(data: Mapping[str, Any], key: str, default: int) -> int:
    value = data.get(key)
    return (
        int(value)
        if isinstance(value, int) and not isinstance(value, bool)
        else default
    )
