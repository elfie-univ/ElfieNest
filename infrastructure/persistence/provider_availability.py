"""Passive App-facing Provider/Endpoint availability query adapter."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone

from app.features.configuration.providers import (
    StoredEndpointCapability,
    StoredModelAvailability,
)
from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.providers.endpoint_capabilities import endpoint_capabilities
from infrastructure.models.storage_ports import ProviderStoragePort, ReportStoragePort
from infrastructure.models.validation.provider_availability import (
    EndpointAvailability,
    project_endpoint_availability,
    project_provider_status,
)
from infrastructure.models.validation.serving_food import ServingFoodIndex


class ProviderAvailabilityQuery:
    """Return projections and coordinate explicitly authorized active checks."""

    def __init__(
        self,
        provider_storage: ProviderStoragePort,
        reports: ReportStoragePort,
        *,
        serving_index: Callable[[], ServingFoodIndex] | None = None,
        active_probe: Callable[[str], object] | None = None,
        config_fingerprint: Callable[[ProviderConnection], str | None] | None = None,
        probe_cooldown: timedelta = timedelta(minutes=5),
    ) -> None:
        self._provider_storage = provider_storage
        self._reports = reports
        self._serving_index = serving_index
        self._active_probe = active_probe
        self._config_fingerprint = config_fingerprint
        self._probe_cooldown = probe_cooldown
        self._probe_lock = threading.Lock()
        self._inflight: dict[str, Future[object]] = {}
        self._last_probe_at: dict[str, datetime] = {}

    def get(self, reference: str) -> StoredModelAvailability:
        connection_id, model_id = _split_reference(reference)
        connections = self._provider_storage.load_connections()
        connection = connections.get(connection_id)
        if connection is None:
            return _unknown(reference, connection_id, model_id, "connection_not_configured")
        model = next(
            (item for item in connection.models if item.endpoint_model_id == model_id),
            None,
        )
        if model is None:
            return _unknown(reference, connection_id, model_id, "model_not_configured")
        return self._project(connection, model, connections)

    def get_many(
        self, references: tuple[str, ...]
    ) -> tuple[StoredModelAvailability, ...]:
        if len(references) > 256:
            raise ValueError("一次最多查询 256 个模型引用")
        return tuple(self.get(reference) for reference in dict.fromkeys(references))

    def ensure(
        self,
        reference: str,
        *,
        max_age: timedelta = timedelta(hours=24),
        allow_probe: bool = False,
    ) -> StoredModelAvailability:
        """Read first; only an explicit active permission can start a probe.

        The single-flight map is process-local.  The validation report remains
        the cross-request fact source, so a second process still converges on
        the same read-time projection after its probe completes.
        """
        current = self.get(reference)
        if not allow_probe or self._active_probe is None:
            return current
        now = datetime.now(timezone.utc)
        observed = _parse_timestamp(current.observed_at)
        if (
            observed is not None
            and now - observed <= max_age
            and current.status in {"available", "degraded"}
        ):
            return current
        with self._probe_lock:
            recent = self._last_probe_at.get(reference)
            if recent is not None and now - recent < self._probe_cooldown:
                return current
            future = self._inflight.get(reference)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[reference] = future
                self._last_probe_at[reference] = now
        if not owner:
            try:
                future.result()
            except BaseException:
                # The owner records the failure in the report boundary.  A
                # concurrent reader still receives the latest projection
                # instead of inheriting an implementation exception.
                pass
            return self.get(reference)
        try:
            future.set_result(self._active_probe(reference))
        except BaseException as error:
            future.set_exception(error)
        finally:
            with self._probe_lock:
                self._inflight.pop(reference, None)
        return self.get(reference)

    def _project(
        self,
        connection: ProviderConnection,
        model: ProviderModelRecord,
        connections: Mapping[str, ProviderConnection],
    ) -> StoredModelAvailability:
        reference = f"{connection.connection_id}/{model.endpoint_model_id}"
        observations = self._reports.observations_for_subject("model", reference)
        fingerprint = self._fingerprint(connection)
        endpoint = project_endpoint_availability(
            reference,
            observations,
            config_fingerprint=fingerprint,
        )
        connection_state = project_endpoint_availability(
            connection.connection_id,
            self._reports.observations_for_subject(
                "provider", connection.connection_id
            ),
            config_fingerprint=fingerprint,
        )
        states = self._connection_states(connection)
        provider_status = project_provider_status(
            states.values(),
            enabled=connection.enabled and not connection.archived,
        )
        connection_block = (
            connection_state
            if connection_state.status == "unavailable"
            and connection_state.error_scope == "connection"
            else None
        ) or next(
            (
                item
                for item in states.values()
                if item.error_scope == "connection" and item.status == "unavailable"
            ),
            None,
        )
        if connection_block is not None:
            provider_status = "unavailable"
        if connection_block is not None and endpoint.status != "unavailable":
            endpoint = EndpointAvailability(
                subject_id=reference,
                status="unavailable",
                reason_code=connection_block.reason_code or "connection_blocked",
                error_scope="connection",
                observed_at=connection_block.observed_at,
                expires_at=None,
                evidence_source=connection_block.evidence_source,
            )
        if not connection.enabled or connection.archived:
            provider_status = "disabled"
        if model.retired:
            endpoint = _lifecycle_endpoint(endpoint, reference, "model_retired")
        elif model.discovery_state == "source_missing":
            endpoint = _lifecycle_endpoint(endpoint, reference, "source_missing")

        serving = self._serving_index() if self._serving_index is not None else None
        core = _core_route(serving, reference)
        return StoredModelAvailability(
            reference=reference,
            connection_id=connection.connection_id,
            model_id=model.endpoint_model_id,
            status=endpoint.status,
            reason_code=endpoint.reason_code,
            provider_status=provider_status,
            evidence_source=endpoint.evidence_source,
            observed_at=endpoint.observed_at,
            expires_at=endpoint.expires_at,
            is_core=core is not None,
            serving_food_ids=() if core is None else core.food_ids,
            serving_roles=() if core is None else core.roles,
            capabilities=tuple(
                StoredEndpointCapability(item.name, item.state, item.evidence)
                for item in endpoint_capabilities(model)
            ),
        )

    def _connection_states(
        self,
        connection: ProviderConnection,
    ) -> dict[str, EndpointAvailability]:
        states: dict[str, EndpointAvailability] = {}
        fingerprint = self._fingerprint(connection)
        for item in connection.models:
            reference = f"{connection.connection_id}/{item.endpoint_model_id}"
            states[reference] = project_endpoint_availability(
                reference,
                self._reports.observations_for_subject("model", reference),
                config_fingerprint=fingerprint,
            )
        return states

    def _fingerprint(self, connection: ProviderConnection) -> str | None:
        if self._config_fingerprint is None:
            return None
        try:
            return self._config_fingerprint(connection)
        except Exception:
            # A malformed configuration must not make a stale observation
            # authoritative.  ``None`` is reserved for legacy in-memory
            # adapters that have no fingerprint source at all; an empty
            # fingerprint rejects all fingerprinted evidence while retaining
            # explicitly unscoped legacy observations.
            return ""


def _split_reference(reference: str) -> tuple[str, str]:
    normalized = reference.strip()
    connection_id, separator, model_id = normalized.partition("/")
    if not separator or not connection_id or not model_id:
        raise ValueError("模型引用必须为 connection_id/model_id")
    return connection_id, model_id


def _unknown(
    reference: str,
    connection_id: str,
    model_id: str,
    reason: str,
) -> StoredModelAvailability:
    return StoredModelAvailability(
        reference=reference,
        connection_id=connection_id,
        model_id=model_id,
        status="unknown",
        reason_code=reason,
        provider_status="unknown",
        evidence_source=None,
        observed_at=None,
        expires_at=None,
        is_core=False,
        serving_food_ids=(),
        serving_roles=(),
        capabilities=(),
    )


def _lifecycle_endpoint(
    current: EndpointAvailability,
    subject_id: str,
    reason: str,
) -> EndpointAvailability:
    return EndpointAvailability(
        subject_id=subject_id,
        status="unavailable",
        reason_code=reason,
        error_scope="endpoint",
        observed_at=current.observed_at,
        expires_at=None,
        evidence_source=current.evidence_source,
        consecutive_transient_failures=current.consecutive_transient_failures,
    )


def _core_route(
    index: ServingFoodIndex | None,
    reference: str,
):
    if index is None:
        return None
    return next(
        (item for item in index.core_endpoints if item.reference == reference),
        None,
    )


__all__ = ("ProviderAvailabilityQuery",)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
