"""Read-time Provider/Endpoint availability projection.

This module is deliberately pure.  It consumes immutable observations and
never performs network I/O or writes a dynamic ``available`` flag back to a
Provider configuration document.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal

from infrastructure.models.report_records import ValidationObservation

AvailabilityStatus = Literal["available", "degraded", "unavailable", "unknown"]
ProviderStatus = Literal[
    "healthy", "degraded", "unavailable", "unknown", "disabled"
]
ErrorScope = Literal["request", "endpoint", "transport", "connection"]

SUCCESS_FRESHNESS = timedelta(hours=24)
TRANSIENT_WINDOW = timedelta(minutes=10)
TRANSIENT_FAILURE_THRESHOLD = 3

_CONNECTION_BLOCK_CODES = frozenset(
    {
        "invalid_credential",
        "credential_revoked",
        "subscription_expired",
        "billing_blocked",
        "account_disabled",
        "quota_exhausted",
    }
)
_ENDPOINT_BLOCK_CODES = frozenset(
    {"model_not_found", "model_not_entitled", "model_retired", "endpoint_disabled"}
)
_REQUEST_NEUTRAL_CODES = frozenset(
    {
        "context_length_exceeded",
        "invalid_request",
        "content_rejected",
        "tool_schema_invalid",
        "request_timeout",
    }
)
_TRANSIENT_CATEGORIES = frozenset({"network", "timeout", "server", "transport"})


@dataclass(frozen=True)
class EndpointAvailability:
    subject_id: str
    status: AvailabilityStatus
    reason_code: str | None
    error_scope: ErrorScope | None
    observed_at: str | None
    expires_at: str | None
    evidence_source: str | None
    consecutive_transient_failures: int = 0


def project_endpoint_availability(
    subject_id: str,
    observations: Iterable[ValidationObservation],
    *,
    now: datetime | None = None,
    config_fingerprint: str | None = None,
) -> EndpointAvailability:
    """Project one exact Endpoint subject with conservative hysteresis."""

    current = _utc(now or datetime.now(timezone.utc))
    scoped_observations = tuple(
        item
        for item in observations
        if config_fingerprint is None
        or item.details.get("config_fingerprint") in {None, config_fingerprint}
    )
    ordered = sorted(
        scoped_observations,
        key=lambda item: (_parse(item.observed_at) or datetime.min.replace(tzinfo=timezone.utc), item.observation_id),
        reverse=True,
    )
    health_observations = [
        item for item in ordered if not _is_request_neutral(item)
    ]
    if not health_observations:
        return EndpointAvailability(
            subject_id,
            "unknown",
            "no_health_evidence",
            None,
            None,
            None,
            None,
        )

    latest = health_observations[0]
    latest_time = _parse(latest.observed_at)
    scope = _error_scope(latest)
    reason = _reason_code(latest)
    source = _evidence_source(latest)

    if _is_connection_block(latest):
        return _snapshot(
            subject_id,
            "unavailable",
            reason or "connection_blocked",
            scope or "connection",
            latest,
            source,
        )
    if _is_endpoint_block(latest):
        return _snapshot(
            subject_id,
            "unavailable",
            reason or "endpoint_blocked",
            scope or "endpoint",
            latest,
            source,
        )

    if latest.status == "passed":
        if latest_time is not None and current - latest_time <= SUCCESS_FRESHNESS:
            return _snapshot(
                subject_id,
                "available",
                "fresh_success",
                None,
                latest,
                source,
                expires_at=_iso(latest_time + SUCCESS_FRESHNESS),
            )
        return _snapshot(
            subject_id,
            "unknown",
            "evidence_expired",
            None,
            latest,
            source,
        )

    if _is_transient(latest):
        failures = _consecutive_transient_failures(health_observations, latest_time)
        if failures >= TRANSIENT_FAILURE_THRESHOLD:
            return _snapshot(
                subject_id,
                "unavailable",
                "transient_failure_threshold",
                scope or "transport",
                latest,
                source,
                consecutive=failures,
            )
        return _snapshot(
            subject_id,
            "degraded",
            reason or "transient_failure",
            scope or "transport",
            latest,
            source,
            expires_at=(
                _iso(latest_time + TRANSIENT_WINDOW)
                if latest_time is not None
                else None
            ),
            consecutive=failures,
        )

    return _snapshot(
        subject_id,
        "degraded",
        reason or "recent_failure",
        scope or "endpoint",
        latest,
        source,
    )


def project_provider_status(
    endpoint_states: Iterable[EndpointAvailability],
    *,
    enabled: bool = True,
    serving_subject_ids: Iterable[str] | None = None,
    transport_failed: bool = False,
) -> ProviderStatus:
    """Aggregate exact Endpoint projections for an Owner-facing Provider state."""

    if not enabled:
        return "disabled"
    states = tuple(endpoint_states)
    serving = None if serving_subject_ids is None else set(serving_subject_ids)
    scoped = tuple(
        item
        for item in states
        if serving is None or item.subject_id in serving
    )
    if not scoped:
        return "unknown"
    transient = tuple(
        item
        for item in scoped
        if item.status in {"degraded", "unavailable"}
        and (
            item.error_scope == "transport"
            or item.reason_code in {"network_error", "timeout", "server_error"}
            or item.reason_code == "transient_failure_threshold"
        )
    )
    if len(transient) >= 2 or (transport_failed and transient):
        return "unavailable"
    if all(item.status == "unknown" for item in scoped):
        return "unknown"
    if all(item.status == "unavailable" for item in scoped):
        return "unavailable"
    if all(item.status == "available" for item in scoped):
        return "healthy"
    return "degraded"


def _snapshot(
    subject_id: str,
    status: AvailabilityStatus,
    reason: str,
    scope: ErrorScope | None,
    observation: ValidationObservation,
    source: str | None,
    *,
    expires_at: str | None = None,
    consecutive: int = 0,
) -> EndpointAvailability:
    return EndpointAvailability(
        subject_id,
        status,
        reason,
        scope,
        observation.observed_at,
        expires_at,
        source,
        consecutive,
    )


def _is_connection_block(observation: ValidationObservation) -> bool:
    return (
        _reason_code(observation) in _CONNECTION_BLOCK_CODES
        or observation.error_category in {"authentication", "billing", "quota"}
        or _error_scope(observation) == "connection"
        and observation.details.get("hard_blocker") is True
    )


def _is_endpoint_block(observation: ValidationObservation) -> bool:
    return _reason_code(observation) in _ENDPOINT_BLOCK_CODES


def _is_request_neutral(observation: ValidationObservation) -> bool:
    if _error_scope(observation) == "request":
        return True
    return _reason_code(observation) in _REQUEST_NEUTRAL_CODES


def _is_transient(observation: ValidationObservation) -> bool:
    return (
        observation.error_category in _TRANSIENT_CATEGORIES
        or _reason_code(observation) in {"network_error", "timeout", "server_error"}
        or _error_scope(observation) == "transport"
    )


def _consecutive_transient_failures(
    observations: list[ValidationObservation],
    latest_time: datetime | None,
) -> int:
    if latest_time is None:
        return 1
    count = 0
    for observation in observations:
        observed_at = _parse(observation.observed_at)
        if observed_at is None or latest_time - observed_at > TRANSIENT_WINDOW:
            break
        if observation.status == "passed" or not _is_transient(observation):
            break
        count += 1
    return max(count, 1)


def _error_scope(observation: ValidationObservation) -> ErrorScope | None:
    raw = observation.details.get("error_scope")
    if isinstance(raw, str) and raw in {
        "request",
        "endpoint",
        "transport",
        "connection",
    }:
        return raw  # type: ignore[return-value]
    if observation.error_category in {"authentication", "billing", "quota"}:
        return "connection"
    if observation.error_category in _TRANSIENT_CATEGORIES:
        return "transport"
    return "endpoint" if observation.status == "failed" else None


def _reason_code(observation: ValidationObservation) -> str | None:
    raw = observation.details.get("error_code") or observation.details.get("reason_code")
    return str(raw) if isinstance(raw, str) and raw else observation.error_category


def _evidence_source(observation: ValidationObservation) -> str | None:
    raw = observation.details.get("evidence_source")
    if isinstance(raw, str) and raw:
        return raw
    mode = observation.details.get("validation_mode")
    if isinstance(mode, str) and mode:
        return "heartbeat" if mode == "heartbeat" else "validation"
    workload = observation.details.get("workload_kind")
    return "production" if workload == "production" else "runtime"


def _parse(value: str) -> datetime | None:
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat()


__all__ = (
    "AvailabilityStatus",
    "EndpointAvailability",
    "ProviderStatus",
    "project_endpoint_availability",
    "project_provider_status",
)
