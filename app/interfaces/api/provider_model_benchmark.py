"""Provider connection/model benchmark validation helpers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import HTTPException

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.storage.provider_connections import ProviderConnection
from ai_runtime.storage.validation_reports import read_latest_provider_validation
from ai_runtime.validation.providers import ProviderValidationRunner, classify_latency

from .provider_schemas import ConnectionBenchmarkCombination

_BENCHMARK_TIMEOUT_SECONDS = 20.0


def validate_combinations(
    combinations: list[ConnectionBenchmarkCombination],
    connections: Dict[str, ProviderConnection],
) -> None:
    for combination in combinations:
        connection = connections.get(combination.connection_id)
        if connection is None or not connection.enabled or connection.archived:
            raise HTTPException(
                status_code=422,
                detail=f"{combination.connection_id} 尚未完成配置",
            )
        verification = read_latest_provider_validation(combination.connection_id)
        if verification.get("status") != "passed":
            raise HTTPException(
                status_code=422,
                detail=f"{combination.connection_id} 尚未验证通过",
            )
        if not any(
            model.endpoint_model_id == combination.model_id
            and not model.hidden
            and not model.retired
            and model.available
            for model in connection.models
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{combination.connection_id} 未声明模型 {combination.model_id}"
                ),
            )


async def bounded_benchmark(
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
