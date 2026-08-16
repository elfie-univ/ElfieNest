"""Persistence implementation of the App Food model-evidence Port."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Optional, cast

from pydantic import JsonValue

from app.features.configuration.food import StoredModelEvidence
from infrastructure.models.food_technology import (
    _project_model,
    validate_food_package_model_references,
)
from infrastructure.models.provider_records import ProviderConnection
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.report_records import ValidationObservation
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.reports.report_repository import ReportRepository


def query_model_evidence(
    *,
    provider_catalog: ProviderCatalog,
    repository: Optional[ReportRepository] = None,
    connection_store: Optional[ProviderConnectionStore] = None,
    connections: Optional[Mapping[str, ProviderConnection]] = None,
    observations: Optional[Sequence[ValidationObservation]] = None,
    now: Optional[datetime] = None,
) -> dict[str, StoredModelEvidence]:
    """Project endpoint models and immutable observations into Food evidence."""
    report_repository = repository or ReportRepository()
    explicit_observations = observations
    current = now or datetime.now(timezone.utc)
    inventory = (
        connections
        if connections is not None
        else (connection_store or ProviderConnectionStore()).load().connections
    )
    result: dict[str, StoredModelEvidence] = {}
    from infrastructure.models.providers.profiles import get_product

    for connection in inventory.values():
        if not connection.enabled or connection.archived:
            continue
        profile = get_product(connection.catalog_id, catalog=provider_catalog)
        is_local = bool(profile and profile.connection_method == "local")
        for model in connection.models:
            subject_id = f"{connection.connection_id}/{model.endpoint_model_id}"
            subject_observations = (
                tuple(
                    item
                    for item in explicit_observations
                    if item.subject_kind == "model" and item.subject_id == subject_id
                )
                if explicit_observations is not None
                else report_repository.observations_for_subject("model", subject_id)
            )
            subject_observations = tuple(
                sorted(
                    subject_observations,
                    key=lambda item: (item.observed_at, item.observation_id),
                    reverse=True,
                )
            )
            base_observation = next(
                (
                    item
                    for item in subject_observations
                    if item.details.get("evidence_kind") != "capability"
                ),
                None,
            )
            capability_observations = tuple(
                item
                for item in subject_observations
                if item.details.get("evidence_kind") == "capability"
            )
            result[subject_id] = _project_model(
                subject_id,
                model,
                base_observation,
                is_local=is_local,
                now=current,
                capability_observations=capability_observations,
            )
    return result


def record_model_evidence(
    evidence: Sequence[StoredModelEvidence],
    *,
    repository: Optional[ReportRepository] = None,
    scope: str,
    trigger: str,
) -> Optional[str]:
    """Append model evidence to the report database's sole writer."""
    if not evidence:
        return None
    report_repository = repository or ReportRepository()
    run_id = report_repository.start_run(scope=scope, trigger=trigger)
    for item in evidence:
        report_repository.append_observation(
            run_id=run_id,
            subject_kind="model",
            subject_id=item.reference,
            observed_at=item.observed_at or None,
            status="passed" if item.verified else "failed",
            latency_ms=item.latency_ms,
            details=cast(
                Mapping[str, JsonValue],
                {
                    "capabilities": sorted(item.capabilities),
                    "cost_grade": item.cost_grade,
                    "tool_test_passed": item.tool_test_passed,
                },
            ),
        )
    report_repository.finish_run(run_id, status="complete")
    return run_id


class SQLiteFoodEvidenceAdapter:
    """Implement FoodEvidencePort with the Provider and report stores."""

    def __init__(
        self,
        connection_store: ProviderConnectionStore,
        report_repository: ReportRepository,
        provider_catalog: ProviderCatalog,
    ) -> None:
        self._connection_store = connection_store
        self._report_repository = report_repository
        self._provider_catalog = provider_catalog

    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]:
        return tuple(
            query_model_evidence(
                provider_catalog=self._provider_catalog,
                connection_store=self._connection_store,
                repository=self._report_repository,
            ).values()
        )

    def record_model_evidence(
        self,
        evidence: Sequence[StoredModelEvidence],
        *,
        scope: str,
        trigger: str,
    ) -> Optional[str]:
        return record_model_evidence(
            evidence,
            repository=self._report_repository,
            scope=scope,
            trigger=trigger,
        )

    def validate_package(self, package) -> None:
        validate_food_package_model_references(
            package,
            self._connection_store.load().connections,
        )


__all__ = (
    "SQLiteFoodEvidenceAdapter",
    "query_model_evidence",
    "record_model_evidence",
)
