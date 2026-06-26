"""Provider 管理 REST API — 服务商配置的增删改查 + 连通性验证。

所有端点通过 ``Depends(require_admin)`` 保护。
Provider 数据存储在 runtime_config.json 的 providers 字段中。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from elfienest.config.runtime_store import read_runtime_config, write_runtime_config
from runtime.config import LLMRuntimeConfig
from runtime.model_catalog import verify_provider
from runtime.provider_profiles import BUILTIN_PROFILES, get_profile

from .admin_routes import require_admin

logger = logging.getLogger("elfienest.manage.provider_routes")

router = APIRouter(prefix="/api/admin/providers", tags=["providers"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_RUNTIME_CONFIG_PATH: Path = _PROJECT_ROOT / "runtime" / "runtime_config.json"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _read_runtime_config() -> Dict[str, Any]:
    """读取 runtime_config.json，不存在时返回空 dict。"""
    return read_runtime_config(_RUNTIME_CONFIG_PATH)


def _write_runtime_config(config: Dict[str, Any]) -> None:
    """写入 runtime_config.json（先备份）。"""
    write_runtime_config(_RUNTIME_CONFIG_PATH, config)


def _build_provider_response(provider_id: str, provider_info: Dict[str, Any]) -> Dict[str, Any]:
    """构建单个 provider 的响应对象。

    合并内置 profile 和用户配置，添加 status 和 api_mode。
    """
    profile = get_profile(provider_id)

    # 基础信息从 profile 获取
    name = profile.name if profile else provider_id
    api_mode = provider_info.get("api_mode") or (profile.api_mode if profile else "chat_completions")
    auth_type = profile.auth_type if profile else "bearer"

    # 用户配置覆盖默认值
    api_base = provider_info.get("api_base", profile.api_base if profile else "")
    api_key = provider_info.get("api_key", "")

    # 判断状态：有 API key 或为 ollama 则 active
    status = "inactive"
    if provider_id == "ollama":
        status = "active"
    elif api_key:
        status = "active"

    return {
        "provider_id": provider_id,
        "name": name,
        "api_base": api_base,
        "api_mode": api_mode,
        "auth_type": auth_type,
        "status": status,
        "has_api_key": bool(api_key),
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

    if not provider_id:
        raise HTTPException(status_code=422, detail="provider_id 不能为空")

    # 验证 api_mode
    valid_modes = ["ollama", "chat_completions", "anthropic_messages"]
    if api_mode not in valid_modes:
        raise HTTPException(
            status_code=422,
            detail=f"api_mode 必须是 {valid_modes} 之一",
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
    }

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

    config["providers"] = providers
    _write_runtime_config(config)

    logger.info("Provider '%s' updated by admin", provider_id)

    return _build_provider_response(provider_id, providers[provider_id])


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

    runtime_config = LLMRuntimeConfig()
    result = verify_provider(provider_id, runtime_config)

    logger.info(
        "Provider '%s' verification: %s (%.2fms)",
        provider_id,
        result["status"],
        result.get("latency_ms", 0) or 0,
    )

    return result
