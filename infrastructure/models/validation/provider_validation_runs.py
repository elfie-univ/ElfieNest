"""Full and heartbeat validation runs for one Provider connection."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Literal, Mapping, cast

from pydantic import JsonValue

from infrastructure.models.provider_errors import sanitize_error
from infrastructure.models.provider_records import ProviderConnection
from infrastructure.models.storage_ports import ReportStoragePort

from .provider_validation_checks import (
    ModelExecutionProjection,
    bounded_connection_model_check,
)
from .provider_validation_execution import connection_api_key
from .provider_validation_policy import (
    ValidationDecision,
    active_validation_models,
)
from .provider_validation_service import _now, _verification_payload

_MODEL_CONCURRENCY = 2
SecretResolver = Callable[[str], str]


async def run_full(
    connection: ProviderConnection,
    decision: ValidationDecision,
    *,
    model_execution_projection: ModelExecutionProjection,
    reports: ReportStoragePort,
    secret_resolver: SecretResolver,
    run_id: str | None,
    trigger: Literal["batch", "single"],
) -> dict[str, Any]:
    owns_run = run_id is None
    started_at = _now()
    if run_id is None:
        run_id = reports.start_run(
            scope=f"connection:{connection.connection_id}:models",
            trigger=trigger,
            started_at=started_at,
        )
    models = active_validation_models(connection)
    model_ids = tuple(model.endpoint_model_id for model in models)
    model_results: list[dict[str, Any]] = []
    promoted_transport_outage = False
    try:

        def record_batch(
            batch: tuple[Any, ...], raw_results: tuple[dict[str, Any], ...]
        ) -> bool:
            nonlocal promoted_transport_outage
            for model, raw in zip(batch, raw_results):
                checked_at = _now()
                status = "passed" if raw.get("status") == "passed" else "failed"
                error = sanitize_error(
                    _optional_text(raw.get("error")),
                    secrets=(
                        connection_api_key(
                            connection,
                            secret_resolver=secret_resolver,
                        ),
                    ),
                )
                latency = raw.get("latency_ms")
                latency_ms = (
                    float(latency) if isinstance(latency, (int, float)) else None
                )
                latency_class = (
                    str(raw.get("latency_class")) if raw.get("latency_class") else None
                )
                reports.write_model_validation_report(
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
                        "evidence_source": "validation",
                        **{
                            key: value
                            for key, value in raw.items()
                            if key in {"error_code", "error_scope", "error_category"}
                        },
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
                        "error_code": raw.get("error_code"),
                        "error_scope": raw.get("error_scope"),
                        "error_category": raw.get("error_category"),
                    }
                )
            transport_failures = sum(
                1
                for item in model_results
                if item.get("error_scope") == "transport"
                or item.get("error_category")
                in {"network", "timeout", "server", "transport"}
            )
            if transport_failures >= 2:
                promoted_transport_outage = True
            return (
                any(raw.get("error_scope") == "connection" for raw in raw_results)
                or promoted_transport_outage
            )

        # Probe the first model alone.  This preserves the account-wide early
        # stop guarantee: a billing/credential block must not start sibling
        # requests.  Once the connection is known to be reachable, the
        # remaining model checks use bounded parallelism.
        blocked = False
        if models:
            first_batch = (models[0],)
            first_raw = await asyncio.gather(
                bounded_connection_model_check(
                    connection,
                    models[0].endpoint_model_id,
                    asyncio.Semaphore(1),
                    model_execution_projection,
                )
            )
            blocked = record_batch(first_batch, tuple(first_raw))
        for offset in range(1, len(models), _MODEL_CONCURRENCY):
            if blocked:
                break
            batch = models[offset : offset + _MODEL_CONCURRENCY]
            semaphore = asyncio.Semaphore(_MODEL_CONCURRENCY)
            raw_results = await asyncio.gather(
                *(
                    bounded_connection_model_check(
                        connection,
                        model.endpoint_model_id,
                        semaphore,
                        model_execution_projection,
                    )
                    for model in batch
                )
            )
            blocked = record_batch(batch, tuple(raw_results))
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
        first_error = next(
            (item for item in model_results if item.get("error_code")), None
        )
        if first_error is not None:
            metadata.update(
                {
                    "error_code": first_error.get("error_code"),
                    "error_scope": first_error.get("error_scope"),
                    "error_category": first_error.get("error_category"),
                }
            )
        if promoted_transport_outage:
            metadata.update(
                {
                    "error_code": "connection_transient_outage",
                    "error_scope": "connection",
                    "error_category": "transport",
                    "hard_blocker": True,
                }
            )
        reports.write_provider_validation_report(
            connection.connection_id,
            status=status,
            checked_at=finished_at,
            latency_ms=None,
            error=error,
            trigger=trigger,
            run_id=run_id,
            details=cast(Mapping[str, JsonValue], metadata),
        )
        if owns_run:
            reports.finish_run(run_id, status="complete", finished_at=finished_at)
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
            reports.finish_run(run_id, status="partial", finished_at=_now())
        raise
    except Exception:  # Report boundary closes owned runs.
        if owns_run:
            reports.finish_run(run_id, status="failed", finished_at=_now())
        raise


async def run_heartbeat(
    connection: ProviderConnection,
    decision: ValidationDecision,
    *,
    model_execution_projection: ModelExecutionProjection,
    reports: ReportStoragePort,
    secret_resolver: SecretResolver,
    trigger: Literal["batch", "single"],
) -> dict[str, Any]:
    started_at = _now()
    run_id = reports.start_run(
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
            model_execution_projection,
        )
        if model_id
        else {"status": "failed", "error": "没有可验证模型"}
    )
    checked_at = _now()
    status = "passed" if raw.get("status") == "passed" else "failed"
    error = sanitize_error(
        _optional_text(raw.get("error")),
        secrets=(connection_api_key(connection, secret_resolver=secret_resolver),),
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
    reports.write_provider_validation_report(
        connection.connection_id,
        status=status,
        checked_at=checked_at,
        latency_ms=_optional_float(raw.get("latency_ms")),
        error=error,
        trigger=trigger,
        run_id=run_id,
        details=cast(Mapping[str, JsonValue], metadata),
    )
    reports.finish_run(run_id, status="complete", finished_at=checked_at)
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


def _optional_text(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _optional_float(value: JsonValue) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
