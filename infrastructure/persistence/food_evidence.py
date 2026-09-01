"""Persistence implementation of the App Food model-evidence Port."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
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
from infrastructure.models.validation.provider_availability import (
    EndpointAvailability,
    project_endpoint_availability,
    project_reachability,
)
from infrastructure.models.validation.provider_validation_policy import (
    connection_reachability_fingerprint,
    connection_validation_fingerprint,
)
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.reports.report_repository import ReportRepository


def query_model_evidence(
    *,
    provider_catalog: ProviderCatalog,
    repository: Optional[ReportRepository] = None,
    connection_store: Optional[ProviderConnectionStore] = None,
    connections: Optional[Mapping[str, ProviderConnection]] = None,
    observations: Optional[Sequence[ValidationObservation]] = None,
    provider_observations: Optional[Sequence[ValidationObservation]] = None,
    secret_resolver: Callable[[str], str] | None = None,
    now: Optional[datetime] = None,
) -> dict[str, StoredModelEvidence]:
    """Project endpoint models and immutable observations into Food evidence."""
    explicit_observations = observations
    report_repository = repository
    if report_repository is None and explicit_observations is None:
        report_repository = ReportRepository()
    current = now or datetime.now(timezone.utc)
    inventory = (
        connections
        if connections is not None
        else (connection_store or ProviderConnectionStore()).load().connections
    )
    result: dict[str, StoredModelEvidence] = {}
    from infrastructure.models.providers.profiles import get_product

    provider_events = provider_observations
    if provider_events is None and report_repository is not None:
        provider_events = tuple(
            event
            for connection in inventory.values()
            for event in report_repository.observations_for_subject(
                "provider", connection.connection_id
            )
        )
    provider_events = tuple(provider_events or ())

    for connection in inventory.values():
        if not connection.enabled or connection.archived:
            continue
        profile = get_product(connection.catalog_id, catalog=provider_catalog)
        is_local = bool(profile and profile.connection_method == "local")
        fingerprint: str | None = None
        if secret_resolver is not None:
            try:
                fingerprint = connection_validation_fingerprint(
                    connection,
                    secret_resolver=secret_resolver,
                )
            except Exception:
                # A malformed current configuration must not make an older
                # fingerprinted observation authoritative. Unscoped legacy
                # evidence remains readable for migration only.
                fingerprint = ""
        provider_block = _provider_block(
            connection,
            provider_events,
            now=current,
            secret_resolver=secret_resolver,
        )
        for model in connection.models:
            subject_id = f"{connection.connection_id}/{model.endpoint_model_id}"
            preference = provider_catalog.food_generation_preference(
                connection.catalog_id,
                model.endpoint_model_id,
            )
            if explicit_observations is not None:
                subject_observations = tuple(
                    item
                    for item in explicit_observations
                    if item.subject_kind == "model" and item.subject_id == subject_id
                )
            else:
                assert report_repository is not None
                subject_observations = report_repository.observations_for_subject(
                    "model", subject_id
                )
            if fingerprint is not None:
                subject_observations = tuple(
                    item
                    for item in subject_observations
                    if item.details.get("config_fingerprint") in {None, fingerprint}
                )
            subject_observations = tuple(
                sorted(
                    subject_observations,
                    key=lambda item: (item.observed_at, item.observation_id),
                    reverse=True,
                )
            )
            capability_observations = tuple(
                item
                for item in subject_observations
                if item.details.get("evidence_kind") == "capability"
            ) + _production_capability_observations(subject_observations)
            base_observation = next(
                (
                    item
                    for item in subject_observations
                    if item.details.get("evidence_kind") != "capability"
                ),
                None,
            )
            result[subject_id] = _project_model(
                subject_id,
                model,
                base_observation,
                is_local=is_local,
                now=current,
                capability_observations=capability_observations,
                provider_block=provider_block,
                auto_selection_priority=(
                    preference.priority if preference is not None else 100
                ),
                quality_tier=preference.quality_tier if preference is not None else 0,
                pricing=profile.pricing_for_model(model.endpoint_model_id)
                if profile is not None
                else model.pricing,
            )
    return result


def _production_capability_observations(
    observations: Sequence[ValidationObservation],
) -> tuple[ValidationObservation, ...]:
    """Promote only feature use actually observed in production calls.

    A successful text call, an image-shaped request, or a Provider accepting
    options is deliberately not enough.  Dispatch metadata has a positive
    signal only for a tool call or an observed reasoning trace, so those are
    the only zero-cost production capability facts emitted here.
    """
    promoted: list[ValidationObservation] = []
    signals = (
        ("tools", "tool_called", "production_tool_call_observed"),
        ("reasoning", "reasoning_observed", "production_reasoning_observed"),
    )
    for observation in observations:
        if (
            observation.subject_kind != "model"
            or observation.status != "passed"
            or observation.details.get("event_type") != "model_call"
            or observation.details.get("workload_kind") != "production"
        ):
            continue
        for capability, signal, reason_code in signals:
            if observation.details.get(signal) is not True:
                continue
            promoted.append(
                replace(
                    observation,
                    details={
                        "evidence_kind": "capability",
                        "capability": capability,
                        "capability_state": "supported",
                        "capability_evidence": "verified",
                        "reason_code": reason_code,
                        "evidence_source": "production",
                        "validation_mode": "production",
                        **(
                            {
                                "config_fingerprint": observation.details[
                                    "config_fingerprint"
                                ]
                            }
                            if observation.details.get("config_fingerprint")
                            else {}
                        ),
                    },
                )
            )
    return tuple(promoted)


def _provider_block(
    connection: ProviderConnection,
    observations: Sequence[ValidationObservation],
    *,
    now: datetime,
    secret_resolver: Callable[[str], str] | None,
) -> EndpointAvailability | None:
    """Return only connection-wide blockers for one Provider connection."""
    scoped = tuple(
        item
        for item in observations
        if item.subject_kind == "provider"
        and item.subject_id == connection.connection_id
    )
    fingerprint: str | None = None
    if not connection.credential_ref.startswith("oauth.") and secret_resolver:
        try:
            fingerprint = connection_validation_fingerprint(
                connection,
                secret_resolver=secret_resolver,
            )
        except Exception:
            # Invalid credentials/configuration must not make old evidence
            # authoritative; the next active validation will publish a new
            # fingerprinted observation.
            fingerprint = ""
    state = project_endpoint_availability(
        connection.connection_id,
        scoped,
        now=now,
        config_fingerprint=fingerprint,
    )
    reachability = project_reachability(
        connection.connection_id,
        scoped,
        now=now,
        config_fingerprint=_reachability_fingerprint(
            connection,
            secret_resolver=secret_resolver,
        ),
    )
    if state.status == "unavailable" and state.error_scope == "connection":
        return state
    if reachability.status == "unavailable":
        return EndpointAvailability(
            subject_id=connection.connection_id,
            status="unavailable",
            reason_code=reachability.reason_code or "provider_unreachable",
            error_scope="connection",
            observed_at=reachability.observed_at,
            expires_at=reachability.expires_at,
            evidence_source=reachability.evidence_source,
            consecutive_transient_failures=reachability.consecutive_transient_failures,
        )
    return None


def _reachability_fingerprint(
    connection: ProviderConnection,
    *,
    secret_resolver: Callable[[str], str] | None,
) -> str | None:
    if secret_resolver is None:
        return None
    try:
        return connection_reachability_fingerprint(
            connection,
            secret_resolver=secret_resolver,
        )
    except Exception:
        return ""


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
        secret_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self._connection_store = connection_store
        self._report_repository = report_repository
        self._provider_catalog = provider_catalog
        self._secret_resolver = secret_resolver

    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]:
        return tuple(
            query_model_evidence(
                provider_catalog=self._provider_catalog,
                connection_store=self._connection_store,
                repository=self._report_repository,
                secret_resolver=self._secret_resolver,
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
