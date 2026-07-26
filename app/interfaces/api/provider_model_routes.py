"""Owner Provider model matrix and bounded benchmark routes."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.models.capabilities import known_capabilities
from ai_runtime.providers.profiles import BUILTIN_PROFILES
from ai_runtime.validation.providers import ProviderValidationRunner, classify_latency
from app.features.accounts.auth import require_owner

from .provider_schemas import BenchmarkCombination, BenchmarkRequest
from .provider_support import (
    is_configured,
    provider_models,
    provider_view,
    read_provider_config,
    runtime_config,
    sanitize_error,
    verification_view,
    write_provider_config,
)

router = APIRouter()
_BENCHMARK_TIMEOUT_SECONDS = 20.0
_BENCHMARK_CONCURRENCY = 2
_BENCHMARK_SLOTS = threading.BoundedSemaphore(_BENCHMARK_CONCURRENCY)


def _configured_provider_items(
    config: Dict[str, Any],
) -> list[tuple[str, Dict[str, Any]]]:
    providers = config.setdefault("providers", {})
    result: list[tuple[str, Dict[str, Any]]] = []
    for provider_id in BUILTIN_PROFILES:
        info = providers.get(provider_id, {})
        if is_configured(provider_id, info):
            result.append((provider_id, info))
    result.extend(
        (provider_id, info)
        for provider_id, info in providers.items()
        if provider_id not in BUILTIN_PROFILES
        and isinstance(info, dict)
        and is_configured(provider_id, info)
    )
    return result


def _matrix(config: Dict[str, Any]) -> dict[str, Any]:
    configured = _configured_provider_items(config)
    provider_views = [
        {
            "provider_id": provider_id,
            "name": provider_view(provider_id, info)["name"],
            "verification": verification_view(info),
        }
        for provider_id, info in configured
    ]
    models_by_provider = {
        provider_id: {item["id"]: item for item in provider_models(info)}
        for provider_id, info in configured
    }
    model_ids = sorted(
        {model_id for items in models_by_provider.values() for model_id in items}
    )
    rows: list[dict[str, Any]] = []
    for model_id in model_ids:
        display_name = next(
            (
                items[model_id]["display_name"]
                for items in models_by_provider.values()
                if model_id in items
            ),
            model_id,
        )
        capabilities = sorted(known_capabilities(model_id, display_name) or {"text"})
        cells: list[dict[str, Any]] = []
        for provider_id, info in configured:
            benchmark = info.get("benchmarks", {}).get(model_id, {})
            latency = benchmark.get("latency_ms")
            cells.append(
                {
                    "provider_id": provider_id,
                    "available": model_id in models_by_provider[provider_id],
                    "verification_status": verification_view(info)["status"],
                    "benchmark_status": benchmark.get("status"),
                    "latency_ms": (
                        float(latency) if isinstance(latency, (int, float)) else None
                    ),
                    "latency_class": benchmark.get("latency_class"),
                    "price_estimate": None,
                }
            )
        rows.append(
            {
                "model_id": model_id,
                "display_name": display_name,
                "capabilities": capabilities,
                "providers": cells,
            }
        )
    return {"providers": provider_views, "models": rows}


@router.get("/model-matrix")
async def model_matrix(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return _matrix(read_provider_config())


def _benchmark_sync(
    combination: BenchmarkCombination, config: Dict[str, Any]
) -> dict[str, Any]:
    if not _BENCHMARK_SLOTS.acquire(blocking=False):
        return {
            "status": "failed",
            "latency_ms": None,
            "latency_class": None,
            "error": "模型测速任务过多，请稍后重试",
        }
    try:
        return _benchmark_sync_with_slot(combination, config)
    finally:
        _BENCHMARK_SLOTS.release()


def _benchmark_sync_with_slot(
    combination: BenchmarkCombination, config: Dict[str, Any]
) -> dict[str, Any]:
    runner = ProviderValidationRunner(runtime_config(config))
    suite = runner.verify_models(
        combination.provider_id,
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


async def run_model_benchmark(
    combination: BenchmarkCombination, config: Dict[str, Any]
) -> dict[str, Any]:
    return await asyncio.to_thread(_benchmark_sync, combination, config)


async def _bounded_benchmark(
    combination: BenchmarkCombination,
    config: Dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async with semaphore:
        try:
            return await asyncio.wait_for(
                run_model_benchmark(combination, config),
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


async def _run_benchmarks(
    combinations: list[BenchmarkCombination], config: Dict[str, Any]
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(_BENCHMARK_CONCURRENCY)
    tasks = [
        asyncio.create_task(_bounded_benchmark(item, config, semaphore))
        for item in combinations
    ]
    try:
        return list(await asyncio.gather(*tasks))
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def _validate_combinations(
    combinations: list[BenchmarkCombination], config: Dict[str, Any]
) -> None:
    providers = config.setdefault("providers", {})
    for item in combinations:
        info = providers.get(item.provider_id, {})
        if not is_configured(item.provider_id, info):
            raise HTTPException(
                status_code=422, detail=f"{item.provider_id} 尚未完成配置"
            )
        if verification_view(info)["status"] != "passed":
            raise HTTPException(
                status_code=422, detail=f"{item.provider_id} 尚未验证通过"
            )
        known_models = {model["id"] for model in provider_models(info)}
        if item.model_id not in known_models:
            raise HTTPException(
                status_code=422,
                detail=f"{item.provider_id} 未声明模型 {item.model_id}",
            )


@router.post("/models/benchmark")
async def benchmark_models(
    body: BenchmarkRequest,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    config = read_provider_config()
    _validate_combinations(body.combinations, config)
    if await request.is_disconnected():
        raise HTTPException(status_code=499, detail="客户端已断开")
    raw_results = await _run_benchmarks(body.combinations, config)
    results: list[dict[str, Any]] = []
    checked_at = datetime.now(timezone.utc).isoformat()
    for combination, raw in zip(body.combinations, raw_results):
        info = config["providers"][combination.provider_id]
        stored = {
            "status": "passed" if raw["status"] == "passed" else "failed",
            "checked_at": checked_at,
            "latency_ms": raw.get("latency_ms"),
            "latency_class": raw.get("latency_class"),
            "error": sanitize_error(
                raw.get("error"), secrets=(str(info.get("api_key") or ""),)
            ),
        }
        info.setdefault("benchmarks", {})[combination.model_id] = stored
        results.append(
            {
                "provider_id": combination.provider_id,
                "model_id": combination.model_id,
                **stored,
            }
        )
    write_provider_config(config)
    return {"results": results}
