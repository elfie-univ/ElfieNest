"""Read-only Provider connection/model matrix projection."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ai_runtime.food.evidence import query_model_evidence
from ai_runtime.models.capabilities import known_capabilities
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderModelRecord,
)
from ai_runtime.storage.report_repository import ValidationObservation
from ai_runtime.storage.validation_reports import read_latest_provider_validation


def build_model_matrix(
    connections: Dict[str, ProviderConnection],
    *,
    observations: tuple[ValidationObservation, ...] = (),
    snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = {(item.subject_kind, item.subject_id): item for item in observations}
    allow_latest_fallback = snapshot is None or snapshot.get("mode") == "current"
    model_evidence = query_model_evidence(
        connections=connections,
        observations=observations,
    )
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
            ),
        }
        for connection in enabled
    ]
    grouped: dict[str, list[tuple[ProviderConnection, ProviderModelRecord]]] = {}
    for connection in enabled:
        for model in connection.models:
            if model.hidden or model.retired:
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
                        )["status"],
                        "benchmark_status": None,
                        "latency_ms": None,
                        "latency_class": None,
                        "price_estimate": None,
                    }
                )
                continue
            subject_id = f"{connection.connection_id}/{entry_model.endpoint_model_id}"
            projected = model_evidence[subject_id]
            capabilities.update(
                projected.capabilities or _model_capabilities(entry_model)
            )
            observation = evidence.get(("model", subject_id))
            cells.append(
                {
                    "connection_id": connection.connection_id,
                    "model_id": entry_model.endpoint_model_id,
                    "available": entry_model.available,
                    "verification_status": _provider_verification(
                        connection.connection_id,
                        evidence.get(("provider", connection.connection_id)),
                        allow_latest_fallback=allow_latest_fallback,
                    )["status"],
                    "benchmark_status": (
                        observation.status if observation is not None else None
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


def _provider_verification(
    connection_id: str,
    observation: Optional[ValidationObservation] = None,
    *,
    allow_latest_fallback: bool = True,
) -> dict[str, Any]:
    latest = (
        _observation_payload(observation)
        if observation is not None
        else read_latest_provider_validation(connection_id)
        if allow_latest_fallback
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
    capabilities = set(
        known_capabilities(model.endpoint_model_id, model.display_name) or {"text"}
    )
    if model.supports_tools:
        capabilities.add("tools")
    if model.supports_vision:
        capabilities.add("vision")
    if model.supports_reasoning:
        capabilities.add("reasoning")
    return capabilities
