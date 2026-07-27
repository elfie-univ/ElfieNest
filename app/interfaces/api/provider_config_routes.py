"""Owner Provider configuration CRUD routes."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ai_runtime.providers.profiles import BUILTIN_PROFILES, get_profile
from ai_runtime.storage.secrets import provider_secret_name, set_provider_secret
from ai_runtime.validation.providers import discover_provider_models
from app.features.accounts.auth import require_owner

from .provider_schemas import ProviderWriteRequest
from .provider_support import (
    provider_view,
    read_provider_config,
    reset_verification,
    runtime_config,
    sanitize_error,
    write_provider_config,
)

logger = logging.getLogger("app.interfaces.api.provider_config_routes")
router = APIRouter()
_BUILTIN_SECRET_NAMES = frozenset(
    provider_secret_name(provider_id) for provider_id in BUILTIN_PROFILES
)
_MODEL_REFRESH_SLOTS = threading.BoundedSemaphore(3)
_MODEL_REFRESH_TIMEOUT_SECONDS = 7.0


def _default_auth_type(api_mode: str) -> str:
    if api_mode == "ollama":
        return "none"
    if api_mode == "anthropic_messages":
        return "x-api-key"
    return "bearer"


def _apply_write(
    provider_id: str, info: Dict[str, Any], body: ProviderWriteRequest
) -> None:
    fields = body.model_fields_set
    profile = get_profile(provider_id)
    if "api_base" in fields:
        info["api_base"] = body.api_base or ""
    elif "api_base" not in info and profile:
        info["api_base"] = profile.api_base
    if "api_key" in fields:
        info["api_key"] = body.api_key or ""
    if "api_mode" in fields:
        info["api_mode"] = body.api_mode
    elif "api_mode" not in info:
        info["api_mode"] = profile.api_mode if profile else "chat_completions"
    if "auth_type" in fields:
        info["auth_type"] = body.auth_type
    elif "auth_type" not in info:
        info["auth_type"] = (
            profile.auth_type if profile else _default_auth_type(str(info["api_mode"]))
        )
    for field_name in ("display_name", "test_model"):
        if field_name not in fields:
            continue
        value = getattr(body, field_name) or ""
        if value:
            info[field_name] = value
        else:
            info.pop(field_name, None)
    if "models" in fields:
        info["models"] = [
            {
                "id": item.id,
                "display_name": item.display_name or item.id,
            }
            for item in body.models or []
        ]
    connection_fields = {
        "api_base",
        "api_key",
        "api_mode",
        "auth_type",
        "test_model",
        "models",
    }
    if fields & connection_fields:
        reset_verification(info)


def _refresh_models(
    provider_id: str, config: Dict[str, Any], *, require_models: bool
) -> None:
    info = config["providers"][provider_id]
    try:
        discovered = discover_provider_models(
            provider_id,
            runtime_config(config),
            timeout=5.0,
            allow_configured_fallback=False,
        )
    except Exception as exc:
        message = sanitize_error(str(exc), secrets=(str(info.get("api_key") or ""),))
        info["model_refresh"] = {"status": "failed", "message": message}
        if require_models:
            raise HTTPException(
                status_code=422,
                detail=f"自动拉取模型失败，请手工填写模型 ID 和显示名：{message}",
            ) from exc
        return
    info["models"] = [
        {"id": item.name, "display_name": item.display_name or item.name}
        for item in discovered
    ]
    info["model_refresh"] = {"status": "updated", "count": len(discovered)}


def _refresh_models_with_slot(
    provider_id: str, config: Dict[str, Any], *, require_models: bool
) -> None:
    if not _MODEL_REFRESH_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="模型发现任务过多，请稍后重试")
    try:
        _refresh_models(provider_id, config, require_models=require_models)
    finally:
        _MODEL_REFRESH_SLOTS.release()


async def _refresh_models_async(
    provider_id: str, config: Dict[str, Any], *, require_models: bool
) -> None:
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                _refresh_models_with_slot,
                provider_id,
                config,
                require_models=require_models,
            ),
            timeout=_MODEL_REFRESH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="模型发现超时") from exc


@router.get("/")
async def list_providers(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> list[dict[str, Any]]:
    _ = owner
    config = read_provider_config()
    providers = config.get("providers", {})
    result = [
        provider_view(provider_id, providers.get(provider_id, {}))
        for provider_id in BUILTIN_PROFILES
    ]
    result.extend(
        provider_view(provider_id, info)
        for provider_id, info in providers.items()
        if provider_id not in BUILTIN_PROFILES and isinstance(info, dict)
    )
    return result


@router.post("/", status_code=201)
async def add_provider(
    body: ProviderWriteRequest,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    provider_id = body.provider_id or ""
    if not provider_id:
        raise HTTPException(status_code=422, detail="provider_id 不能为空")
    config = read_provider_config()
    providers = config.setdefault("providers", {})
    if provider_id in BUILTIN_PROFILES:
        raise HTTPException(status_code=409, detail="内置 Provider 请使用修改操作")
    if provider_secret_name(provider_id) in _BUILTIN_SECRET_NAMES:
        raise HTTPException(status_code=409, detail="provider_id 与内置密钥命名冲突")
    if any(
        existing_id != provider_id
        and provider_secret_name(existing_id) == provider_secret_name(provider_id)
        for existing_id in providers
    ):
        raise HTTPException(status_code=409, detail="provider_id 与现有密钥命名冲突")
    if provider_id in providers:
        raise HTTPException(status_code=409, detail=f"provider '{provider_id}' 已存在")
    info: Dict[str, Any] = {}
    _apply_write(provider_id, info, body)
    providers[provider_id] = info
    if body.refresh_models:
        await _refresh_models_async(
            provider_id,
            config,
            require_models=not bool(info.get("models") or info.get("test_model")),
        )
    write_provider_config(config)
    logger.info("Provider '%s' added by owner", provider_id)
    return provider_view(provider_id, info)


@router.put("/{provider_id}")
async def update_provider(
    provider_id: str,
    body: ProviderWriteRequest,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    if "provider_id" in body.model_fields_set:
        raise HTTPException(status_code=422, detail="provider_id 不可修改")
    config = read_provider_config()
    providers = config.setdefault("providers", {})
    if provider_id not in providers and provider_id not in BUILTIN_PROFILES:
        raise HTTPException(status_code=404, detail=f"provider '{provider_id}' 不存在")
    info = providers.setdefault(provider_id, {})
    _apply_write(provider_id, info, body)
    if body.refresh_models:
        await _refresh_models_async(provider_id, config, require_models=False)
    write_provider_config(config)
    logger.info("Provider '%s' updated by owner", provider_id)
    return provider_view(provider_id, info)


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, str]:
    _ = owner
    if provider_id == "ollama":
        raise HTTPException(status_code=400, detail="不能删除内置的 ollama provider")
    config = read_provider_config()
    providers = config.get("providers", {})
    if provider_id not in providers:
        raise HTTPException(
            status_code=404, detail=f"provider '{provider_id}' 无配置可删除"
        )
    del providers[provider_id]
    write_provider_config(config)
    set_provider_secret(provider_id, "")
    logger.info("Provider '%s' deleted by owner", provider_id)
    return {"detail": f"provider '{provider_id}' 已删除"}
