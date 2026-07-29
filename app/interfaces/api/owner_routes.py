"""Owner-only runtime configuration endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ai_runtime.storage.data_home import get_config_path
from app.features.accounts.auth import (
    get_current_user,
    require_owner,
)
from app.features.configuration.runtime_store import (
    read_runtime_config,
)

logger = logging.getLogger("app.interfaces.api.owner_routes")

__all__ = ("get_current_user", "require_owner", "router")

router = APIRouter(prefix="/api/owner", tags=["owner"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

# ===================================================================
# LLM 配置管理
# ===================================================================


@router.get("/config")
async def get_config(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    """读取 ``ELFIE_HOME/configs/`` 下的合并 Runtime 配置。

    文件可能不存在（gitignored 且尚未创建），此时返回 ``{}``。
    解析失败同样返回 ``{}``。
    """
    _ = owner
    return read_runtime_config(get_config_path())


@router.put("/config")
async def update_config(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    """Reject the retired raw writer; typed section routes own all mutations."""
    _ = body, owner
    raise HTTPException(
        status_code=410,
        detail="原始配置写入口已停用，请使用供应商、粮食和系统设置页面",
    )
