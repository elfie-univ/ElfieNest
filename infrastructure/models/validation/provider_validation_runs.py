"""Full and heartbeat validation runs for one Provider connection."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from infrastructure.models.provider_errors import sanitize_error
from infrastructure.persistence.provider_connections import ProviderConnection
from infrastructure.persistence.reports.report_repository import ReportRepository
from infrastructure.persistence.reports.validation_reports import (
    write_model_validation_report,
    write_provider_validation_report,
)

from .provider_validation_checks import (
    RuntimeProjection,
    bounded_connection_model_check,
)
from .provider_validation_policy import (
    ValidationDecision,
    active_validation_models,
)
from .provider_validation_runtime import connection_api_key
from .provider_validation_service import _now, _verification_payload

_MODEL_CONCURRENCY = 2


async def run_full(
    connection: ProviderConnection,
    decision: ValidationDecision,
    *,
    runtime_projection: RuntimeProjection,
    run_id: str | None,
    trigger: Literal["batch", "single"],
) -> dict[str, Any]:
    repository = ReportRepository()
    owns_run = run_id is None
    started_at = _now()
    if run_id is None:
        run_id = repository.start_run(
            scope=f"connection:{connection.connection_id}:models",
            trigger=trigger,
            started_at=started_at,
        )
    models = active_validation_models(connection)
    model_ids = tuple(model.endpoint_model_id for model in models)
    model_results: list[dict[str, Any]] = []
    try:
        semaphore = asyncio.Semaphore(_MODEL_CONCURRENCY)
        for model in models:
            raw = await bounded_connection_model_check(
                connection,
                model.endpoint_model_id,
                semaphore,
                runtime_projection,
            )
            checked_at = _now()
            status = "passed" if raw.get("status") == "passed" else "failed"
            error = sanitize_error(
                raw.get("error"),
                secrets=(connection_api_key(connection),),
            )
            latency = raw.get("latency_ms")
            latency_ms = float(latency) if isinstance(latency, (int, float)) else None
            latency_class = (
                str(raw.get("latency_class")) if raw.get("latency_class") else None
            )
            write_model_validation_report(
                connection.connection_id,
                model.endpoint_model_id,
                status=status,
                checked_at=checked_at,
                latency_ms=latency_ms,
                latency_class=latency_class,
                error=error,
                trigger="full",
                run_id=run_id,
                details={
                    "validation_mode": "full",
                    "full_run_id": run_id,
                    "config_fingerprint": decision.fingerprint,
                },
            )
            model_results.append(
                {
                    "model_id": model.endpoint_model_id,
                    "status": status,
                    "checked_at": checked_at,
                    "latency_ms": latency_ms,
                    "latency_class": latency_class,
                    "error": error,
                }
            )
        finished_at = _now()
        status = (
            "passed"
            if model_results
            and all(item["status"] == "passed" for item in model_results)
            else "failed"
        )
        error = next(
            (item["error"] for item in model_results if item["error"]),
            "没有可验证模型" if not model_results else None,
        )
        metadata = {
            "validation_mode": "full",
            "full_run_id": run_id,
            "full_checked_at": finished_at,
            "full_status": status,
            "config_fingerprint": decision.fingerprint,
            "model_ids": sorted(model_ids),
            "model_count": len(model_results),
            "passed_count": sum(
                1 for item in model_results if item["status"] == "passed"
            ),
        }
        write_provider_validation_report(
            connection.connection_id,
            status=status,
            checked_at=finished_at,
            latency_ms=None,
            error=error,
            trigger=trigger,
            run_id=run_id,
            details=metadata,
        )
        if owns_run:
            repository.finish_run(run_id, status="complete", finished_at=finished_at)
        return _verification_payload(
            status=status,
            checked_at=finished_at,
            latency_ms=None,
            error=error,
            validation_mode="full",
            cache_hit=False,
            decision=decision,
            full_run_id=run_id,
            full_checked_at=finished_at,
            model_results=model_results,
            model_count=len(model_results),
            passed_count=sum(1 for item in model_results if item["status"] == "passed"),
        )
    except asyncio.CancelledError:
        if owns_run:
            repository.finish_run(run_id, status="partial", finished_at=_now())
        raise
    except Exception:  # Report boundary closes owned runs.
        if owns_run:
            repository.finish_run(run_id, status="failed", finished_at=_now())
        raise


async def run_heartbeat(
    connection: ProviderConnection,
    decision: ValidationDecision,
    *,
    runtime_projection: RuntimeProjection,
    trigger: Literal["batch", "single"],
) -> dict[str, Any]:
    repository = ReportRepository()
    started_at = _now()
    run_id = repository.start_run(
        scope=f"connection:{connection.connection_id}:heartbeat",
        trigger=trigger,
        started_at=started_at,
    )
    model_id = decision.representative_model_id
    raw = (
        await bounded_connection_model_check(
            connection,
            model_id,
            asyncio.Semaphore(1),
            runtime_projection,
        )
        if model_id
        else {"status": "failed", "error": "没有可验证模型"}
    )
    checked_at = _now()
    status = "passed" if raw.get("status") == "passed" else "failed"
    error = sanitize_error(
        raw.get("error"),
        secrets=(connection_api_key(connection),),
    )
    metadata = {
        "validation_mode": "heartbeat",
        "full_run_id": decision.source_run_id,
        "full_checked_at": decision.full_checked_at,
        "full_status": decision.full_status,
        "heartbeat_checked_at": checked_at,
        "heartbeat_status": status,
        "representative_model_id": model_id,
        "config_fingerprint": decision.fingerprint,
        "model_ids": [
            model.endpoint_model_id for model in active_validation_models(connection)
        ],
    }
    write_provider_validation_report(
        connection.connection_id,
        status=status,
        checked_at=checked_at,
        latency_ms=(
            float(raw["latency_ms"])
            if isinstance(raw.get("latency_ms"), (int, float))
            else None
        ),
        error=error,
        trigger=trigger,
        run_id=run_id,
        details=metadata,
    )
    repository.finish_run(run_id, status="complete", finished_at=checked_at)
    return _verification_payload(
        status=status,
        checked_at=checked_at,
        latency_ms=raw.get("latency_ms"),
        error=error,
        validation_mode="heartbeat",
        cache_hit=False,
        decision=decision,
        heartbeat_checked_at=checked_at,
        heartbeat_status=status,
        model_id=model_id,
    )
