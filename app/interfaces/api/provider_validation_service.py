"""Connection-level model validation and cost-aware report orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from ai_runtime.storage.provider_connections import ProviderConnection
from ai_runtime.storage.validation_reports import read_latest_provider_validation

from .provider_validation_checks import RuntimeProjection
from .provider_validation_policy import (
    ValidationDecision,
    active_validation_models,
    choose_validation_mode,
    representative_model_id,
)

ValidationTrigger = Literal["single", "batch"]


async def validate_connection(
    connection: ProviderConnection,
    *,
    runtime_projection: RuntimeProjection,
    run_id: str | None = None,
    trigger: ValidationTrigger = "single",
    force_full: bool = False,
) -> dict[str, Any]:
    """Validate one connection using cache, heartbeat, or full model checks."""
    from .provider_validation_runs import run_full, run_heartbeat

    latest = read_latest_provider_validation(connection.connection_id)
    decision = choose_validation_mode(connection, latest, force_full=force_full)
    if decision.mode == "cached":
        return _cached_result(latest, decision)
    if decision.mode == "heartbeat":
        return await run_heartbeat(
            connection,
            decision,
            runtime_projection=runtime_projection,
            trigger=trigger,
        )
    return await run_full(
        connection,
        decision,
        runtime_projection=runtime_projection,
        run_id=run_id,
        trigger=trigger,
    )


def summarize_connection_validation(
    connection: ProviderConnection,
) -> dict[str, Any]:
    """Project current validation freshness without making a network request."""
    latest = read_latest_provider_validation(connection.connection_id)
    if not latest:
        return {
            "status": "never",
            "checked_at": None,
            "latency_ms": None,
            "error": None,
            "validation_mode": "none",
            "cache_hit": False,
            "needs_full_validation": bool(active_validation_models(connection)),
            "needs_heartbeat": False,
            "full_run_id": None,
            "full_checked_at": None,
            "heartbeat_checked_at": None,
            "representative_model_id": representative_model_id(connection),
        }
    decision = choose_validation_mode(connection, latest)
    metadata = latest.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    heartbeat_checked_at = metadata.get("heartbeat_checked_at")
    heartbeat_age = _age_since(heartbeat_checked_at)
    return _verification_payload(
        status=str(latest.get("status") or "never"),
        checked_at=latest.get("checked_at"),
        latency_ms=latest.get("latency_ms"),
        error=latest.get("error"),
        validation_mode=decision.mode,
        cache_hit=decision.mode == "cached",
        decision=decision,
        heartbeat_checked_at=heartbeat_checked_at,
        heartbeat_status=(
            str(metadata.get("heartbeat_status"))
            if metadata.get("validation_mode") == "heartbeat"
            and metadata.get("heartbeat_status")
            else None
        ),
        needs_heartbeat=(
            decision.mode == "heartbeat"
            and (heartbeat_age is None or heartbeat_age > 24 * 60 * 60)
        ),
        needs_full_validation=decision.mode == "full",
    )


def _cached_result(
    latest: dict[str, Any],
    decision: ValidationDecision,
) -> dict[str, Any]:
    metadata = latest.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return _verification_payload(
        status=str(latest.get("status") or "failed"),
        checked_at=latest.get("checked_at"),
        latency_ms=latest.get("latency_ms"),
        error=latest.get("error"),
        validation_mode="cached",
        cache_hit=True,
        decision=decision,
        heartbeat_checked_at=metadata.get("heartbeat_checked_at"),
        heartbeat_status=metadata.get("heartbeat_status"),
    )


def _verification_payload(
    *,
    status: str,
    checked_at: Any,
    latency_ms: Any,
    error: Any,
    validation_mode: str,
    cache_hit: bool,
    decision: ValidationDecision,
    full_run_id: str | None = None,
    full_checked_at: str | None = None,
    heartbeat_checked_at: str | None = None,
    heartbeat_status: str | None = None,
    needs_heartbeat: bool = False,
    needs_full_validation: bool = False,
    model_id: str | None = None,
    model_results: list[dict[str, Any]] | None = None,
    model_count: int | None = None,
    passed_count: int | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "checked_at": checked_at,
        "latency_ms": latency_ms,
        "error": error,
        "validation_mode": validation_mode,
        "cache_hit": cache_hit,
        "needs_full_validation": needs_full_validation,
        "needs_heartbeat": needs_heartbeat,
        "full_run_id": full_run_id or decision.source_run_id,
        "full_checked_at": full_checked_at or decision.full_checked_at,
        "heartbeat_checked_at": heartbeat_checked_at,
        "heartbeat_status": heartbeat_status,
        "representative_model_id": model_id or decision.representative_model_id,
        "reason": decision.reason,
        "model_results": model_results or [],
        "model_count": model_count,
        "passed_count": passed_count,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_since(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        checked_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - checked_at.astimezone(timezone.utc)
    return max(age.total_seconds(), 0.0)
