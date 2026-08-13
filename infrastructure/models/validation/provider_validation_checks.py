"""Bounded configured-model smoke checks for Provider validation."""

from __future__ import annotations

import asyncio
from typing import Callable

from pydantic import JsonValue

from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.provider_records import ProviderConnection
from infrastructure.models.validation.provider_validation import (
    ProviderValidationRunner,
    classify_latency,
)
from infrastructure.models.validation.validation_models import CheckStatus

ModelExecutionProjection = Callable[[ProviderConnection], tuple[str, ModelExecutionConfig]]
_MODEL_TIMEOUT_SECONDS = 20.0


def run_connection_model_check(
    connection: ProviderConnection,
    model_id: str,
    model_execution_projection: ModelExecutionProjection,
) -> dict[str, JsonValue]:
    """Execute one configured model through the normal Provider adapter."""
    execution_id, config = model_execution_projection(connection)
    suite = ProviderValidationRunner(config).verify_models(
        execution_id,
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
    model_execution_projection: ModelExecutionProjection,
) -> dict[str, JsonValue]:
    """Bound one model request without retrying or spending extra tokens."""
    async with semaphore:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    run_connection_model_check,
                    connection,
                    model_id,
                    model_execution_projection,
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
