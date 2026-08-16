"""Read-only Provider connection/model matrix projection."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.features.configuration.food import StoredModelEvidence
from app.features.configuration.providers import (
    CapabilityName,
    StoredEndpointCapability,
)
from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.providers.endpoint_capabilities import endpoint_capabilities
from infrastructure.models.report_records import ValidationObservation


def build_model_matrix(
    connections: Dict[str, ProviderConnection],
    *,
    observations: tuple[ValidationObservation, ...] = (),
    model_evidence: Mapping[str, StoredModelEvidence] | None = None,
    provider_validation_reader: Callable[[str], Mapping[str, object]] | None = None,
    snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = _latest_observations(observations)
    allow_latest_fallback = snapshot is None or snapshot.get("mode") == "current"
    projected_evidence = dict(model_evidence or {})
    enabled = [
        connection
        for connection in connections.values()
        if connection.enabled and not connection.archived
    ]
    connection_views = [
        {
            "connection_id": connection.connection_id,
            "name": connection.alias,
            "verification": _provider_verification(
                connection.connection_id,
                evidence.get(("provider", connection.connection_id)),
                allow_latest_fallback=allow_latest_fallback,
                provider_validation_reader=provider_validation_reader,
            ),
        }
        for connection in enabled
    ]
    grouped: dict[str, list[tuple[ProviderConnection, ProviderModelRecord]]] = {}
    for connection in enabled:
        for model in connection.models:
            # Source-managed models omitted by a complete authoritative
            # refresh belong to the obsolete view, not the normal comparison
            # matrix.  Keep exact availability queries able to address them,
            # but do not make the normal inventory look larger or less useful.
            if model.hidden or model.retired or model.discovery_state != "present":
                continue
            grouped.setdefault(_model_identity(model), []).append((connection, model))
    rows: list[dict[str, Any]] = []
    for identity, entries in sorted(
        grouped.items(),
        key=lambda item: item[1][0][1].display_name.casefold(),
    ):
        display_name = entries[0][1].display_name
        entries_by_connection = {
            connection.connection_id: model for connection, model in entries
        }
        cells: list[dict[str, Any]] = []
        capabilities: set[str] = set()
        for connection in enabled:
            entry_model = entries_by_connection.get(connection.connection_id)
            if entry_model is None:
                cells.append(
                    {
                        "connection_id": connection.connection_id,
                        "model_id": None,
                        "available": False,
                        "verification_status": _provider_verification(
                            connection.connection_id,
                            evidence.get(("provider", connection.connection_id)),
                            allow_latest_fallback=allow_latest_fallback,
                            provider_validation_reader=provider_validation_reader,
                        )["status"],
                        "benchmark_status": None,
                        "latency_ms": None,
                        "latency_class": None,
                        "price_estimate": None,
                        "locality": _locality(connection),
                        "validated_at": None,
                        "time_to_first_token_ms": None,
                        "total_latency_ms": None,
                        "context_window_tokens": None,
                        "max_output_tokens": None,
                        "validation_source": None,
                        "capability_facts": [],
                    }
                )
                continue
            subject_id = f"{connection.connection_id}/{entry_model.endpoint_model_id}"
            projected = projected_evidence.get(subject_id)
            projected_for_cell = projected if allow_latest_fallback else None
            subject_observations = tuple(
                item
                for item in observations
                if item.subject_kind == "model" and item.subject_id == subject_id
            )
            capabilities.update(_model_capabilities(entry_model))
            capabilities.update(_observed_capabilities(subject_observations))
            if projected_for_cell is not None:
                capabilities.update(projected_for_cell.capabilities)
            observation = evidence.get(("model", subject_id))
            capability_facts = _capability_facts(
                entry_model,
                projected_for_cell,
                subject_observations,
            )
            validation_status = _validation_status(observation, projected_for_cell)
            cells.append(
                {
                    "connection_id": connection.connection_id,
                    "model_id": entry_model.endpoint_model_id,
                    "available": (
                        not entry_model.hidden
                        and not entry_model.retired
                        and entry_model.discovery_state == "present"
                    ),
                    # This is deliberately exact-endpoint evidence.  Provider
                    # verification is shown in the separate connection row;
                    # it must not make every model under that connection pass.
                    "verification_status": validation_status,
                    "benchmark_status": (
                        observation.status
                        if observation is not None
                        and observation.status in {"passed", "failed"}
                        else None
                    ),
                    "latency_ms": (
                        observation.latency_ms if observation is not None else None
                    ),
                    "latency_class": (
                        observation.details.get("latency_class")
                        if observation is not None
                        else None
                    ),
                    "price_estimate": None,
                    "locality": _locality(connection),
                    "validated_at": (
                        observation.observed_at
                        if observation is not None
                        else projected_for_cell.observed_at
                        if projected_for_cell is not None
                        and projected_for_cell.observed_at
                        else None
                    ),
                    "time_to_first_token_ms": (
                        observation.time_to_first_token_ms
                        if observation is not None
                        else None
                    ),
                    "total_latency_ms": (
                        observation.latency_ms if observation is not None else None
                    ),
                    "context_window_tokens": entry_model.context_window_tokens,
                    "max_output_tokens": entry_model.max_output_tokens,
                    "validation_source": (
                        str(observation.details.get("evidence_source"))
                        if observation is not None
                        and observation.details.get("evidence_source")
                        else None
                    ),
                    "capability_facts": [
                        {
                            "name": item.name,
                            "state": item.state,
                            "evidence": item.evidence,
                        }
                        for item in capability_facts
                    ],
                }
            )
        rows.append(
            {
                "model_key": identity,
                "display_name": display_name,
                "capabilities": sorted(capabilities or {"text"}),
                "connections": cells,
            }
        )
    return {
        "snapshot": snapshot or {"mode": "current"},
        "connections": connection_views,
        "models": rows,
    }


def _latest_observations(
    observations: tuple[ValidationObservation, ...],
) -> dict[tuple[str, str], ValidationObservation]:
    latest: dict[tuple[str, str], ValidationObservation] = {}
    for observation in observations:
        # Capability probes share the exact model subject but are a separate
        # evidence channel.  They must not replace the text/availability
        # observation used for the health, latency, and validation columns.
        if observation.details.get("evidence_kind") == "capability":
            continue
        key = (observation.subject_kind, observation.subject_id)
        previous = latest.get(key)
        if previous is None or _observation_sort_key(
            observation
        ) > _observation_sort_key(previous):
            latest[key] = observation
    return latest


def _observation_sort_key(
    observation: ValidationObservation,
) -> tuple[datetime, int]:
    try:
        timestamp = datetime.fromisoformat(
            observation.observed_at.replace("Z", "+00:00")
        )
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
    except ValueError:
        timestamp = datetime.min.replace(tzinfo=timezone.utc)
    return timestamp, observation.observation_id


def _locality(connection: ProviderConnection) -> str:
    return (
        "local"
        if connection.api_mode == "ollama" or connection.catalog_id == "ollama"
        else "remote"
    )


def _validation_status(
    observation: ValidationObservation | None,
    projected: StoredModelEvidence | None,
) -> str:
    if observation is not None:
        return "passed" if observation.status == "passed" else "failed"
    if projected is not None:
        if projected.status == "verified":
            return "passed"
        if projected.status in {"failed", "unavailable"}:
            return "failed"
    return "never"


def _capability_facts(
    model: ProviderModelRecord,
    projected: StoredModelEvidence | None,
    observations: tuple[ValidationObservation, ...] = (),
) -> tuple[StoredEndpointCapability, ...]:
    observed = _latest_capability_facts(observations)
    facts: list[StoredEndpointCapability] = []
    capability_names: tuple[CapabilityName, ...] = (
        "tools",
        "vision",
        "reasoning",
        "structured_output",
    )
    for name in capability_names:
        observed_fact = observed.get(name)
        state = (
            observed_fact[0]
            if observed_fact is not None
            else projected.capability_states.get(name)
            if projected
            else None
        )
        if state is None:
            configured = getattr(model, f"supports_{name}")
            state = (
                "supported"
                if configured is True
                else "unsupported"
                if configured is False
                else "unknown"
            )
        evidence = (
            observed_fact[1]
            if observed_fact is not None
            else model.capability_evidence.get(name, "unknown")
        )
        facts.append(
            StoredEndpointCapability(
                name=name,
                state=state,  # type: ignore[arg-type]
                evidence=evidence,  # type: ignore[arg-type]
            )
        )
    return tuple(facts)


def _latest_capability_facts(
    observations: tuple[ValidationObservation, ...],
) -> dict[str, tuple[str, str]]:
    latest: dict[str, ValidationObservation] = {}
    for observation in observations:
        if observation.details.get("evidence_kind") != "capability":
            continue
        name = observation.details.get("capability")
        state = observation.details.get("capability_state")
        evidence = observation.details.get("capability_evidence")
        if not (
            isinstance(name, str)
            and isinstance(state, str)
            and isinstance(evidence, str)
        ):
            continue
        if name not in {"tools", "vision", "reasoning", "structured_output"}:
            continue
        if state not in {"supported", "unsupported", "unknown"}:
            continue
        if evidence not in {
            "declared",
            "declared_by_user",
            "accepted",
            "verified",
            "unknown",
        }:
            continue
        previous = latest.get(name)
        if previous is None or _observation_sort_key(
            observation
        ) > _observation_sort_key(previous):
            latest[name] = observation
    return {
        name: (
            str(observation.details["capability_state"]),
            str(observation.details["capability_evidence"]),
        )
        for name, observation in latest.items()
    }


def _observed_capabilities(
    observations: tuple[ValidationObservation, ...],
) -> set[str]:
    return {
        name
        for name, (state, evidence) in _latest_capability_facts(observations).items()
        if state == "supported" and evidence in {"declared", "verified"}
    }


def _provider_verification(
    connection_id: str,
    observation: Optional[ValidationObservation] = None,
    *,
    allow_latest_fallback: bool = True,
    provider_validation_reader: Callable[[str], Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    latest = (
        _observation_payload(observation)
        if observation is not None
        else provider_validation_reader(connection_id)
        if allow_latest_fallback and provider_validation_reader is not None
        else {}
    )
    return {
        "status": latest.get("status", "never"),
        "checked_at": latest.get("checked_at"),
        "latency_ms": latest.get("latency_ms"),
        "error": latest.get("error"),
    }


def _observation_payload(
    observation: ValidationObservation,
) -> dict[str, Any]:
    return {
        "status": observation.status,
        "checked_at": observation.observed_at,
        "latency_ms": observation.latency_ms,
        "latency_class": observation.details.get("latency_class"),
        "error": observation.error_message,
    }


def _model_identity(model: ProviderModelRecord) -> str:
    if model.canonical_model_id:
        return model.canonical_model_id
    normalized = re.sub(r"[^a-z0-9]+", "", model.display_name.casefold())
    return f"display:{normalized or model.endpoint_model_id.casefold()}"


def _model_capabilities(model: ProviderModelRecord) -> set[str]:
    # This is an exact connection/model cell.  Canonical identity metadata
    # cannot grant capabilities that this endpoint did not declare or verify.
    capabilities = {"text"}
    for capability in endpoint_capabilities(model):
        if capability.state == "supported" and capability.evidence in {
            "declared",
            "verified",
        }:
            capabilities.add(capability.name)
    return capabilities
