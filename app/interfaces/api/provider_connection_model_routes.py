"""Model comparison and benchmarks for stable Provider connections."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.report_repository import ReportRepository
from ai_runtime.storage.secrets import connection_secret_name, resolve_secret
from ai_runtime.storage.validation_reports import write_model_validation_report
from app.interfaces.api.v1.auth import require_manager
from infrastructure.models.provider_errors import sanitize_error
from infrastructure.models.provider_model_benchmark import (
    bounded_benchmark,
    validate_combinations,
)
from infrastructure.models.provider_model_matrix import build_model_matrix

from .provider_connection_routes import _verify_connection_in_run
from .provider_schemas import (
    ConnectionBenchmarkRequest,
)

router = APIRouter()
_BENCHMARK_CONCURRENCY = 2


@router.get("/connection-model-matrix")
async def connection_model_matrix(
    as_of: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    repository = ReportRepository()
    if as_of and run_id:
        raise HTTPException(status_code=422, detail="as_of 和 run_id 不能同时使用")
    try:
        observations = (
            repository.observations_for_run(run_id)
            if run_id
            else repository.as_of(as_of)
            if as_of
            else repository.current()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="无效的报告快照时间") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="报告快照不存在") from exc
    snapshot = {
        "mode": "run" if run_id else "as_of" if as_of else "current",
        "run_id": run_id,
        "as_of": as_of,
    }
    if run_id:
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="报告运行不存在") from exc
        snapshot.update(
            {
                "status": run.status,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
        )
    return build_model_matrix(
        ProviderConnectionStore().load().connections,
        observations=observations,
        snapshot=snapshot,
    )


@router.post("/connection-models/benchmark")
async def benchmark_connection_models(
    body: ConnectionBenchmarkRequest,
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    connections = ProviderConnectionStore().load().connections
    try:
        validate_combinations(body.combinations, connections)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if await request.is_disconnected():
        raise HTTPException(status_code=499, detail="客户端已断开")
    semaphore = asyncio.Semaphore(_BENCHMARK_CONCURRENCY)
    tasks = [
        asyncio.create_task(
            bounded_benchmark(item, connections[item.connection_id], semaphore)
        )
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
    repository = ReportRepository()
    run_id = repository.start_run(
        scope="model-selection",
        trigger="benchmark",
        started_at=checked_at,
    )
    results: list[dict[str, Any]] = []
    for combination, raw in zip(body.combinations, raw_results):
        connection = connections[combination.connection_id]
        secret_name = connection.credential_ref or connection_secret_name(
            combination.connection_id
        )
        stored_status = "passed" if raw["status"] == "passed" else "failed"
        latency = raw.get("latency_ms")
        latency_ms = float(latency) if isinstance(latency, (int, float)) else None
        latency_class = str(raw["latency_class"]) if raw.get("latency_class") else None
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
            run_id=run_id,
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
    repository.finish_run(run_id, status="complete", finished_at=checked_at)
    return {"run_id": run_id, "status": "complete", "results": results}


@router.post("/connection-models/validate-all")
async def validate_all_connection_models(
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    connections = [
        connection
        for connection in ProviderConnectionStore().load().connections.values()
        if connection.enabled and not connection.archived
    ]
    repository = ReportRepository()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = repository.start_run(
        scope="all-enabled-connections-and-models",
        trigger="validate_all",
        started_at=started_at,
    )
    results: list[dict[str, Any]] = []
    status = "complete"
    try:
        for connection in connections:
            if await request.is_disconnected():
                status = "partial"
                break
            verification = await _verify_connection_in_run(
                connection,
                run_id=run_id,
                trigger="batch",
                force_full=True,
            )
            results.append(
                {
                    "subject": f"provider:{connection.connection_id}",
                    **verification,
                }
            )
            for model_result in verification.get("model_results", []):
                model_id = str(model_result["model_id"])
                results.append(
                    {
                        "subject": (f"model:{connection.connection_id}/{model_id}"),
                        **model_result,
                    }
                )
    except asyncio.CancelledError:
        status = "partial"
        raise
    except Exception:
        status = "partial" if results else "failed"
        raise
    finally:
        repository.finish_run(
            run_id,
            status=status,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
    return {"run_id": run_id, "status": status, "results": results}
