"""Owner Provider single and bounded batch validation routes."""

from __future__ import annotations

import asyncio
import logging
import threading
import urllib.error
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.models.catalog import _verify_custom_openai_provider, verify_provider
from ai_runtime.providers.profiles import BUILTIN_PROFILES
from ai_runtime.usage.observer import (
    ProviderVerifyObservation,
    RuntimeEventStatus,
    get_runtime_observer,
)
from app.features.accounts.auth import require_owner

from .provider_schemas import VerifyBatchRequest
from .provider_support import (
    is_configured,
    read_provider_config,
    runtime_config,
    stored_verification,
    write_provider_config,
)

logger = logging.getLogger("app.interfaces.api.provider_validation_routes")
router = APIRouter()
_PROVIDER_TIMEOUT_SECONDS = 15.0
_PROVIDER_CONCURRENCY = 3
_VERIFY_SLOTS = threading.BoundedSemaphore(_PROVIDER_CONCURRENCY)


def _verify_sync(provider_id: str, config: Dict[str, Any]) -> dict[str, Any]:
    if not _VERIFY_SLOTS.acquire(blocking=False):
        return {
            "status": "failed",
            "latency_ms": None,
            "error": "Provider 验证任务过多，请稍后重试",
        }
    try:
        return _verify_sync_with_slot(provider_id, config)
    finally:
        _VERIFY_SLOTS.release()


def _verify_sync_with_slot(provider_id: str, config: Dict[str, Any]) -> dict[str, Any]:
    providers = config.get("providers", {})
    info = providers.get(provider_id, {})
    if provider_id not in BUILTIN_PROFILES:
        if info.get("api_mode", "chat_completions") != "chat_completions":
            raise ValueError("自定义供应商验证当前仅支持 OpenAI 兼容 Chat Completions")
        try:
            return _verify_custom_openai_provider(
                info,
                str(info.get("api_base", "")),
                str(info.get("api_key", "")),
            )
        except urllib.error.URLError as exc:
            return {
                "status": "failed",
                "latency_ms": None,
                "error": f"连接失败: {exc.reason}",
            }
    return verify_provider(provider_id, runtime_config(config))


async def run_provider_check(
    provider_id: str, config: Dict[str, Any]
) -> dict[str, Any]:
    return await asyncio.to_thread(_verify_sync, provider_id, config)


def _store_result(
    provider_id: str, config: Dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    info = config.setdefault("providers", {}).setdefault(provider_id, {})
    latency = result.get("latency_ms")
    verification = stored_verification(
        status=str(result.get("status") or "failed"),
        latency_ms=float(latency) if isinstance(latency, (int, float)) else None,
        error=str(result["error"]) if result.get("error") else None,
        secrets=(str(info.get("api_key") or ""),),
    )
    info["verification"] = verification
    event_status = (
        RuntimeEventStatus.OK
        if verification["status"] == "passed"
        else RuntimeEventStatus.ERROR
    )
    get_runtime_observer().record_provider_verify(
        ProviderVerifyObservation(
            provider_id=provider_id,
            status=event_status,
            provider_status=verification["status"],
            latency_ms=float(verification["latency_ms"] or 0.0),
            error=str(verification["error"] or ""),
        )
    )
    return verification


async def _bounded_check(
    provider_id: str,
    config: Dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async with semaphore:
        try:
            return await asyncio.wait_for(
                run_provider_check(provider_id, config),
                timeout=_PROVIDER_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "latency_ms": None,
                "error": "验证超时（15 秒）",
            }
        except ValueError as exc:
            return {"status": "failed", "latency_ms": None, "error": str(exc)}
        except Exception as exc:
            logger.warning(
                "Provider '%s' validation failed", provider_id, exc_info=True
            )
            return {
                "status": "failed",
                "latency_ms": None,
                "error": f"验证失败: {type(exc).__name__}",
            }


async def _run_tasks(
    provider_ids: list[str], config: Dict[str, Any]
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(_PROVIDER_CONCURRENCY)
    tasks = [
        asyncio.create_task(_bounded_check(provider_id, config, semaphore))
        for provider_id in provider_ids
    ]
    try:
        return list(await asyncio.gather(*tasks))
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


@router.post("/verify-batch")
async def verify_batch(
    body: VerifyBatchRequest,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    config = read_provider_config()
    providers = config.setdefault("providers", {})
    requested = body.provider_ids or [
        provider_id
        for provider_id in BUILTIN_PROFILES
        if is_configured(provider_id, providers.get(provider_id, {}))
    ] + [
        provider_id
        for provider_id, info in providers.items()
        if provider_id not in BUILTIN_PROFILES
        and isinstance(info, dict)
        and is_configured(provider_id, info)
    ]
    if len(requested) > 10:
        raise HTTPException(status_code=422, detail="单批最多验证 10 个 Provider")
    configured_ids = [
        provider_id
        for provider_id in requested
        if is_configured(provider_id, providers.get(provider_id, {}))
    ]
    if await request.is_disconnected():
        raise HTTPException(status_code=499, detail="客户端已断开")
    checked = await _run_tasks(configured_ids, config)
    checked_by_id = dict(zip(configured_ids, checked))
    results: list[dict[str, Any]] = []
    for provider_id in requested:
        if provider_id not in checked_by_id:
            results.append(
                {
                    "provider_id": provider_id,
                    "configured": False,
                    "status": "skipped",
                    "verification": None,
                }
            )
            continue
        verification = _store_result(provider_id, config, checked_by_id[provider_id])
        results.append(
            {
                "provider_id": provider_id,
                "configured": True,
                "status": verification["status"],
                "verification": verification,
            }
        )
    write_provider_config(config)
    return {"results": results}


@router.post("/{provider_id}/verify")
async def verify_one(
    provider_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    config = read_provider_config()
    providers = config.setdefault("providers", {})
    if provider_id not in BUILTIN_PROFILES and provider_id not in providers:
        raise HTTPException(status_code=404, detail=f"provider '{provider_id}' 不存在")
    if not is_configured(provider_id, providers.get(provider_id, {})):
        raise HTTPException(status_code=422, detail="Provider 尚未完成配置")
    raw = await _bounded_check(provider_id, config, asyncio.Semaphore(1))
    verification = _store_result(provider_id, config, raw)
    write_provider_config(config)
    return {"provider_id": provider_id, "verification": verification}
