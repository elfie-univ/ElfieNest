"""Provider connection/model benchmark validation helpers."""

from __future__ import annotations

import asyncio
from typing import Callable, Protocol

from pydantic import JsonValue

from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.provider_records import ProviderConnection

from .provider_validation_checks import run_connection_model_check

_BENCHMARK_TIMEOUT_SECONDS = 20.0
ModelExecutionProjection = Callable[
    [ProviderConnection], tuple[str, ModelExecutionConfig]
]


class BenchmarkCombination(Protocol):
    @property
    def connection_id(self) -> str: ...

    @property
    def model_id(self) -> str: ...


def validate_combinations(
    combinations: list[BenchmarkCombination],
    connections: dict[str, ProviderConnection],
) -> None:
    for combination in combinations:
        connection = connections.get(combination.connection_id)
        if connection is None or not connection.enabled or connection.archived:
            raise ValueError(f"{combination.connection_id} 尚未完成配置")
        if not any(
            model.endpoint_model_id == combination.model_id
            and not model.hidden
            and not model.retired
            for model in connection.models
        ):
            raise ValueError(
                f"{combination.connection_id} 未声明模型 {combination.model_id}"
            )


async def bounded_benchmark(
    combination: BenchmarkCombination,
    connection: ProviderConnection,
    semaphore: asyncio.Semaphore,
    *,
    model_execution_projection: ModelExecutionProjection,
) -> dict[str, JsonValue]:
    async with semaphore:
        try:
            return await asyncio.wait_for(
                run_connection_model_benchmark(
                    combination,
                    connection,
                    model_execution_projection=model_execution_projection,
                ),
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
    combination: BenchmarkCombination,
    connection: ProviderConnection,
    *,
    model_execution_projection: ModelExecutionProjection,
) -> dict[str, JsonValue]:
    return await asyncio.to_thread(
        _benchmark_sync, combination, connection, model_execution_projection
    )


def _benchmark_sync(
    combination: BenchmarkCombination,
    connection: ProviderConnection,
    model_execution_projection: ModelExecutionProjection,
) -> dict[str, JsonValue]:
    return run_connection_model_check(
        connection,
        combination.model_id,
        model_execution_projection,
    )
