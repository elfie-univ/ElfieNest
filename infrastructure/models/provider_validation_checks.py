"""Bounded configured-model smoke checks for Provider validation."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.validation.models import CheckStatus
from ai_runtime.validation.providers import ProviderValidationRunner, classify_latency
from infrastructure.persistence.provider_connections import ProviderConnection

RuntimeProjection = Callable[[ProviderConnection], tuple[str, LLMRuntimeConfig]]
_MODEL_TIMEOUT_SECONDS = 20.0


def run_connection_model_check(
    connection: ProviderConnection,
    model_id: str,
    runtime_projection: RuntimeProjection,
) -> dict[str, Any]:
    """Execute one configured model through the normal Provider adapter."""
    runtime_id, config = runtime_projection(connection)
    suite = ProviderValidationRunner(config).verify_models(
        runtime_id,
        [model_id],
        max_models=1,
    )
    if not suite.results:
        return {
            "status": "failed",
            "latency_ms": None,
            "latency_class": None,
            "error": "模型验证没有返回结果",
        }
    result = suite.results[0]
    latency_ms = result.duration_ms
    return {
        "status": result.status.value,
        "latency_ms": latency_ms,
        "latency_class": classify_latency(float(latency_ms or 0.0)),
        "error": None if result.status is CheckStatus.PASSED else result.message,
    }


async def bounded_connection_model_check(
    connection: ProviderConnection,
    model_id: str,
    semaphore: asyncio.Semaphore,
    runtime_projection: RuntimeProjection,
) -> dict[str, Any]:
    """Bound one model request without retrying or spending extra tokens."""
    async with semaphore:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    run_connection_model_check,
                    connection,
                    model_id,
                    runtime_projection,
                ),
                timeout=_MODEL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "latency_ms": None,
                "latency_class": None,
                "error": "模型验证超时（20 秒）",
            }
        except Exception as exc:  # Model boundary normalizes provider failures.
            return {
                "status": "failed",
                "latency_ms": None,
                "latency_class": None,
                "error": f"模型验证失败: {type(exc).__name__}",
            }
