"""Model comparison and benchmarks for stable Provider connections."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.models.capabilities import known_capabilities
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.secrets import connection_secret_name, resolve_secret
from ai_runtime.storage.validation_reports import (
    read_latest_model_validation,
    read_latest_provider_validation,
    write_model_validation_report,
)
from ai_runtime.validation.providers import ProviderValidationRunner, classify_latency
from app.features.accounts.auth import require_owner

from .provider_schemas import (
    ConnectionBenchmarkCombination,
    ConnectionBenchmarkRequest,
)
from .provider_support import sanitize_error

router = APIRouter()
_BENCHMARK_TIMEOUT_SECONDS = 20.0
_BENCHMARK_CONCURRENCY = 2


@router.get("/connection-model-matrix")
async def connection_model_matrix(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return _matrix(ProviderConnectionStore().load().connections)


@router.post("/connection-models/benchmark")
async def benchmark_connection_models(
    body: ConnectionBenchmarkRequest,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    connections = ProviderConnectionStore().load().connections
    _validate_combinations(body.combinations, connections)
    if await request.is_disconnected():
        raise HTTPException(status_code=499, detail="客户端已断开")
    semaphore = asyncio.Semaphore(_BENCHMARK_CONCURRENCY)
    tasks = [
        asyncio.create_task(_bounded_benchmark(item, semaphore))
        for item in body.combinations
    ]
    try:
        raw_results = list(await asyncio.gather(*tasks))
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    checked_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    for combination, raw in zip(body.combinations, raw_results):
        connection = connections[combination.connection_id]
        secret_name = connection.credential_ref or connection_secret_name(
            combination.connection_id
        )
        stored_status = "passed" if raw["status"] == "passed" else "failed"
        latency = raw.get("latency_ms")
        latency_ms = float(latency) if isinstance(latency, (int, float)) else None
        latency_class = (
            str(raw["latency_class"]) if raw.get("latency_class") else None
        )
        error = sanitize_error(
            raw.get("error"),
            secrets=(resolve_secret(secret_name),),
        )
        write_model_validation_report(
            combination.connection_id,
            combination.model_id,
            status=stored_status,
            checked_at=checked_at,
            latency_ms=latency_ms,
            latency_class=latency_class,
            error=error,
            trigger="benchmark",
        )
        results.append(
            {
                "connection_id": combination.connection_id,
                "model_id": combination.model_id,
                "status": stored_status,
                "checked_at": checked_at,
                "latency_ms": latency_ms,
                "latency_class": latency_class,
                "error": error,
            }
        )
    return {"results": results}


def _matrix(
    connections: Dict[str, ProviderConnection],
) -> dict[str, Any]:
    enabled = [connection for connection in connections.values() if connection.enabled]
    connection_views = [
        {
            "connection_id": connection.connection_id,
            "name": connection.alias,
            "verification": _provider_verification(connection.connection_id),
        }
        for connection in enabled
    ]
    grouped: dict[str, list[tuple[ProviderConnection, ProviderModelRecord]]] = {}
    for connection in enabled:
        for model in connection.models:
            if model.hidden:
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
            model = entries_by_connection.get(connection.connection_id)
            if model is None:
                cells.append(
                    {
                        "connection_id": connection.connection_id,
                        "model_id": None,
                        "available": False,
                        "verification_status": _provider_verification(
                            connection.connection_id
                        )["status"],
                        "benchmark_status": None,
                        "latency_ms": None,
                        "latency_class": None,
                        "price_estimate": None,
                    }
                )
                continue
            capabilities.update(_model_capabilities(model))
            benchmark = read_latest_model_validation(
                connection.connection_id,
                model.endpoint_model_id,
            )
            cells.append(
                {
                    "connection_id": connection.connection_id,
                    "model_id": model.endpoint_model_id,
                    "available": True,
                    "verification_status": _provider_verification(
                        connection.connection_id
                    )["status"],
                    "benchmark_status": benchmark.get("status"),
                    "latency_ms": benchmark.get("latency_ms"),
                    "latency_class": benchmark.get("latency_class"),
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
    return {"connections": connection_views, "models": rows}


def _provider_verification(connection_id: str) -> dict[str, Any]:
    latest = read_latest_provider_validation(connection_id)
    return {
        "status": latest.get("status", "never"),
        "checked_at": latest.get("checked_at"),
        "latency_ms": latest.get("latency_ms"),
        "error": latest.get("error"),
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


def _validate_combinations(
    combinations: list[ConnectionBenchmarkCombination],
    connections: Dict[str, ProviderConnection],
) -> None:
    for combination in combinations:
        connection = connections.get(combination.connection_id)
        if connection is None or not connection.enabled:
            raise HTTPException(
                status_code=422,
                detail=f"{combination.connection_id} 尚未完成配置",
            )
        verification = _provider_verification(combination.connection_id)
        if verification["status"] != "passed":
            raise HTTPException(
                status_code=422,
                detail=f"{combination.connection_id} 尚未验证通过",
            )
        if not any(
            model.endpoint_model_id == combination.model_id and not model.hidden
            for model in connection.models
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{combination.connection_id} 未声明模型 "
                    f"{combination.model_id}"
                ),
            )


async def _bounded_benchmark(
    combination: ConnectionBenchmarkCombination,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async with semaphore:
        try:
            return await asyncio.wait_for(
                run_connection_model_benchmark(combination),
                timeout=_BENCHMARK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "latency_ms": None,
                "latency_class": None,
                "error": "模型测速超时（20 秒）",
            }
        except Exception as exc:
            return {
                "status": "failed",
                "latency_ms": None,
                "latency_class": None,
                "error": f"模型测速失败: {type(exc).__name__}",
            }


async def run_connection_model_benchmark(
    combination: ConnectionBenchmarkCombination,
) -> dict[str, Any]:
    return await asyncio.to_thread(_benchmark_sync, combination)


def _benchmark_sync(
    combination: ConnectionBenchmarkCombination,
) -> dict[str, Any]:
    suite = ProviderValidationRunner(LLMRuntimeConfig()).verify_models(
        combination.connection_id,
        [combination.model_id],
        max_models=1,
    )
    result = suite.results[0]
    latency = result.duration_ms
    return {
        "status": result.status.value,
        "latency_ms": latency,
        "latency_class": classify_latency(float(latency or 0.0)),
        "error": None if result.status.value == "passed" else result.message,
    }
