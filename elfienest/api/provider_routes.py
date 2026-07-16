"""Provider 管理 REST API — 服务商配置的增删改查 + 连通性验证。

所有端点通过 ``Depends(require_admin)`` 保护。
Provider 数据存储在 runtime_config.json 的 providers 字段中。
"""

from __future__ import annotations

import logging
import urllib.error
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from elfienest.config.runtime_store import (
    hydrate_runtime_secrets,
    read_runtime_config,
    write_runtime_config,
)
from runtime.config import LLMRuntimeConfig
from runtime.models.catalog import _verify_custom_openai_provider, verify_provider
from runtime.providers.model_hints import configured_model_specs
from runtime.providers.profiles import BUILTIN_PROFILES, get_profile
from runtime.storage.data_home import get_config_path
from runtime.usage.observer import (
    ProviderVerifyObservation,
    RuntimeEventStatus,
    get_runtime_observer,
)
from runtime.validation.providers import discover_provider_models

from .admin_routes import require_admin

logger = logging.getLogger("elfienest.api.provider_routes")

router = APIRouter(prefix="/api/admin/providers", tags=["providers"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_RUNTIME_CONFIG_PATH: Path = get_config_path()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _read_runtime_config() -> Dict[str, Any]:
    """读取配置并仅在内部注入本地密钥。"""
    config = read_runtime_config(_RUNTIME_CONFIG_PATH)
    if _RUNTIME_CONFIG_PATH.suffix in {".yaml", ".yml"}:
        return hydrate_runtime_secrets(config)
    return config


def _write_runtime_config(config: Dict[str, Any]) -> None:
    """写入 runtime_config.json（先备份）。"""
    write_runtime_config(_RUNTIME_CONFIG_PATH, config)


def _default_auth_type(api_mode: str) -> str:
    if api_mode == "ollama":
        return "none"
    if api_mode == "anthropic_messages":
        return "x-api-key"
    return "bearer"


def _build_provider_response(provider_id: str, provider_info: Dict[str, Any]) -> Dict[str, Any]:
    """构建单个 provider 的响应对象。

    合并内置 profile 和用户配置，添加 status 和 api_mode。
    """
    profile = get_profile(provider_id)

    # 基础信息从 profile 获取
    name = profile.name if profile else provider_id
    api_mode = provider_info.get("api_mode") or (profile.api_mode if profile else "chat_completions")
    auth_type = provider_info.get("auth_type") or (profile.auth_type if profile else "bearer")

    # 用户配置覆盖默认值
    display_name = provider_info.get("display_name") or provider_info.get("name") or ""
    api_base = provider_info.get("api_base", profile.api_base if profile else "")
    api_key = provider_info.get("api_key", "")
    test_model = provider_info.get("test_model", "")
    model_specs = configured_model_specs(provider_info)

    # 判断状态：有 API key 或为 ollama 则 active
    status = str(provider_info.get("status") or "inactive")
    if provider_id == "ollama":
        status = "active"
    elif api_key:
        status = "active"

    return {
        "provider_id": provider_id,
        "name": display_name or name,
        "display_name": display_name,
        "api_base": api_base,
        "api_mode": api_mode,
        "auth_type": auth_type,
        "test_model": test_model,
        "status": status,
        "has_api_key": bool(api_key),
        "models": [
            {"id": item.model_id, "display_name": item.display_name}
            for item in model_specs
        ],
        "model_refresh": provider_info.get("model_refresh", {}),
    }


# ===================================================================
# 路由：GET /api/admin/providers
# ===================================================================


@router.get("/")
async def list_providers(
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> list:
    """列出所有 provider（内置 + 用户配置）。

    返回每个 provider 的状态、api_mode 等元数据。
    """
    _ = admin

    config = _read_runtime_config()
    providers = config.get("providers", {})

    result = []

    # 添加所有内置 provider
    for provider_id in BUILTIN_PROFILES:
        provider_info = providers.get(provider_id, {})
        result.append(_build_provider_response(provider_id, provider_info))

    # 添加用户自定义 provider（不在内置列表中的）
    for provider_id, provider_info in providers.items():
        if provider_id not in BUILTIN_PROFILES:
            result.append(_build_provider_response(provider_id, provider_info))

    return result


# ===================================================================
# 路由：POST /api/admin/providers
# ===================================================================


@router.post("/", status_code=201)
async def add_provider(
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """添加新的 provider 配置。

    Body: {"provider_id": "openai", "api_base": "...", "api_key": "...", "api_mode": "chat_completions"}
    """
    _ = admin

    provider_id = (body.get("provider_id") or "").strip()
    api_base = (body.get("api_base") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    api_mode = body.get("api_mode", "chat_completions")
    auth_type = body.get("auth_type") or ""
    display_name = (body.get("display_name") or "").strip()
    test_model = (body.get("test_model") or "").strip()
    manual_models = _parse_manual_models(body.get("models"))

    if not provider_id:
        raise HTTPException(status_code=422, detail="provider_id 不能为空")

    # 验证 api_mode
    valid_modes = ["ollama", "chat_completions", "anthropic_messages"]
    if api_mode not in valid_modes:
        raise HTTPException(
            status_code=422,
            detail=f"api_mode 必须是 {valid_modes} 之一",
        )
    valid_auth_types = ["none", "bearer", "x-api-key"]
    if auth_type and auth_type not in valid_auth_types:
        raise HTTPException(
            status_code=422,
            detail=f"auth_type 必须是 {valid_auth_types} 之一",
        )

    config = _read_runtime_config()
    if "providers" not in config:
        config["providers"] = {}

    # 检查是否已存在
    if provider_id in config["providers"]:
        raise HTTPException(status_code=409, detail=f"provider '{provider_id}' 已存在")

    # 添加新 provider
    config["providers"][provider_id] = {
        "api_base": api_base,
        "api_key": api_key,
        "api_mode": api_mode,
        "auth_type": auth_type or _default_auth_type(api_mode),
        "status": "active" if api_key or api_mode == "ollama" else "inactive",
    }
    if display_name:
        config["providers"][provider_id]["display_name"] = display_name
    if test_model:
        config["providers"][provider_id]["test_model"] = test_model
    if manual_models:
        config["providers"][provider_id]["models"] = manual_models
    if body.get("refresh_models") is True:
        _refresh_provider_models(provider_id, config, require_models=not manual_models and not test_model)

    _write_runtime_config(config)
    logger.info("Provider '%s' added by admin", provider_id)

    return _build_provider_response(provider_id, config["providers"][provider_id])


# ===================================================================
# 路由：PUT /api/admin/providers/{provider_id}
# ===================================================================


@router.put("/{provider_id}")
async def update_provider(
    provider_id: str,
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """更新 provider 配置。

    Body 可选字段: api_key, api_base, api_mode
    """
    _ = admin

    config = _read_runtime_config()
    providers = config.get("providers", {})

    # 内置 provider 允许更新，自定义 provider 必须存在
    if provider_id not in providers and provider_id not in BUILTIN_PROFILES:
        raise HTTPException(status_code=404, detail=f"provider '{provider_id}' 不存在")

    # 确保 providers 字典中有该 provider
    if provider_id not in providers:
        providers[provider_id] = {}

    # 更新字段
    if "api_key" in body:
        providers[provider_id]["api_key"] = body["api_key"] or ""
    if "api_base" in body:
        providers[provider_id]["api_base"] = (body["api_base"] or "").strip()
    if "api_mode" in body:
        api_mode = body["api_mode"]
        valid_modes = ["ollama", "chat_completions", "anthropic_messages"]
        if api_mode not in valid_modes:
            raise HTTPException(
                status_code=422,
                detail=f"api_mode 必须是 {valid_modes} 之一",
            )
        providers[provider_id]["api_mode"] = api_mode
        providers[provider_id].setdefault("auth_type", _default_auth_type(api_mode))
    if "auth_type" in body:
        auth_type = body["auth_type"] or ""
        valid_auth_types = ["none", "bearer", "x-api-key"]
        if auth_type not in valid_auth_types:
            raise HTTPException(
                status_code=422,
                detail=f"auth_type 必须是 {valid_auth_types} 之一",
            )
        providers[provider_id]["auth_type"] = auth_type
    if "display_name" in body:
        display_name = (body["display_name"] or "").strip()
        if display_name:
            providers[provider_id]["display_name"] = display_name
        else:
            providers[provider_id].pop("display_name", None)
    if "test_model" in body:
        test_model = (body["test_model"] or "").strip()
        if test_model:
            providers[provider_id]["test_model"] = test_model
        else:
            providers[provider_id].pop("test_model", None)
    if "models" in body:
        providers[provider_id]["models"] = _parse_manual_models(body.get("models"))
    if providers[provider_id].get("api_key") or providers[provider_id].get("api_mode") == "ollama":
        providers[provider_id]["status"] = "active"
    else:
        providers[provider_id]["status"] = "inactive"

    config["providers"] = providers
    if body.get("refresh_models") is True:
        _refresh_provider_models(provider_id, config, require_models=False)
    _write_runtime_config(config)

    logger.info("Provider '%s' updated by admin", provider_id)

    return _build_provider_response(provider_id, providers[provider_id])


def _parse_manual_models(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail="models 必须是数组")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="models 项必须包含 id 和 display_name")
        model_id = str(item.get("id") or item.get("model_id") or "").strip()
        display_name = str(item.get("display_name") or model_id).strip()
        if model_id:
            result.append({"id": model_id, "display_name": display_name})
    return list({item["id"]: item for item in result}.values())


def _refresh_provider_models(
    provider_id: str,
    config: Dict[str, Any],
    *,
    require_models: bool,
) -> None:
    runtime_config = LLMRuntimeConfig()
    runtime_config.providers.update(
        {
            key: value
            for key, value in config.get("providers", {}).items()
            if isinstance(value, dict)
        }
    )
    provider = config["providers"][provider_id]
    try:
        discovered = discover_provider_models(
            provider_id,
            runtime_config,
            timeout=5.0,
            allow_configured_fallback=False,
        )
    except Exception as exc:
        provider["model_refresh"] = {"status": "failed", "message": str(exc)}
        if require_models:
            raise HTTPException(
                status_code=422,
                detail=f"自动拉取模型失败，请手工填写模型 ID 和显示名：{exc}",
            ) from exc
        return
    provider["models"] = [
        {"id": item.name, "display_name": item.display_name or item.name}
        for item in discovered
    ]
    provider["model_refresh"] = {
        "status": "updated",
        "count": len(discovered),
    }


# ===================================================================
# 路由：DELETE /api/admin/providers/{provider_id}
# ===================================================================


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """删除 provider 配置（仅删除用户配置，内置 profile 保留）。"""
    _ = admin

    # 不允许删除 ollama（始终可用）
    if provider_id == "ollama":
        raise HTTPException(status_code=400, detail="不能删除内置的 ollama provider")

    config = _read_runtime_config()
    providers = config.get("providers", {})

    if provider_id not in providers:
        # 如果是内置 provider 但无自定义配置，返回 404
        if provider_id in BUILTIN_PROFILES:
            raise HTTPException(
                status_code=404,
                detail=f"provider '{provider_id}' 无自定义配置可删除",
            )
        raise HTTPException(status_code=404, detail=f"provider '{provider_id}' 不存在")

    # 删除
    del config["providers"][provider_id]
    _write_runtime_config(config)

    logger.info("Provider '%s' deleted by admin", provider_id)

    return {"detail": f"provider '{provider_id}' 已删除"}


# ===================================================================
# 路由：POST /api/admin/providers/{provider_id}/verify
# ===================================================================


@router.post("/{provider_id}/verify")
async def verify_provider_endpoint(
    provider_id: str,
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """验证 provider 连通性。

    通过 HTTP 请求检查 provider 是否可达和可用。
    返回: {"status": "active"|"inactive"|"unverified", "latency_ms": float|None, "error": str|None}
    """
    _ = admin

    config = _read_runtime_config()
    providers = config.get("providers", {})

    if provider_id not in BUILTIN_PROFILES and provider_id not in providers:
        raise HTTPException(status_code=404, detail=f"provider '{provider_id}' 不存在")

    provider_info = providers.get(provider_id, {})
    if provider_id not in BUILTIN_PROFILES and isinstance(provider_info, dict):
        api_mode = provider_info.get("api_mode", "chat_completions")
        if api_mode != "chat_completions":
            raise HTTPException(
                status_code=422,
                detail="自定义供应商验证当前仅支持 OpenAI 兼容 Chat Completions",
            )
        try:
            result = _verify_custom_openai_provider(
                provider_info,
                str(provider_info.get("api_base", "")),
                str(provider_info.get("api_key", "")),
            )
        except urllib.error.URLError as exc:
            result = {
                "status": "inactive",
                "latency_ms": None,
                "error": f"连接失败: {exc.reason}",
            }
    else:
        runtime_config = LLMRuntimeConfig()
        runtime_config.providers.update({
            key: value
            for key, value in providers.items()
            if isinstance(value, dict)
        })
        result = verify_provider(provider_id, runtime_config)
    provider_status = str(result.get("status", "unverified"))
    event_status = (
        RuntimeEventStatus.OK
        if provider_status == "active"
        else RuntimeEventStatus.ERROR
    )
    get_runtime_observer().record_provider_verify(
        ProviderVerifyObservation(
            provider_id=provider_id,
            status=event_status,
            provider_status=provider_status,
            latency_ms=float(result.get("latency_ms") or 0.0),
            error=str(result.get("error") or ""),
        )
    )

    logger.info(
        "Provider '%s' verification: %s (%.2fms)",
        provider_id,
        result["status"],
        result.get("latency_ms", 0) or 0,
    )

    return result
