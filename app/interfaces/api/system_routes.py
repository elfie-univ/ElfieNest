"""系统设置 REST API — 3 个 section 的 GET/PUT 端点。

使用方式::

    from .system_routes import router as system_router
    app.include_router(system_router)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Final

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.storage.data_home import get_config_path
from app.features.configuration.runtime_store import (
    read_system_section,
    write_system_section,
)
from app.interfaces.api.v1.auth import require_manager

logger = logging.getLogger("app.interfaces.api.system_routes")

router = APIRouter(prefix="/api/owner/system", tags=["system"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 可用的 section 白名单
# ---------------------------------------------------------------------------

VALID_SECTIONS = frozenset({"adoption", "engine", "security"})
MAX_ELFIES_PER_MACHINE: Final = 32

# ---------------------------------------------------------------------------
# 各 section 字段类型期望（用于 PUT 校验）
# ---------------------------------------------------------------------------

# 内部辅助：校验嵌套字典（如 security.rate_limit）
_SECTION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "adoption": {
        "max_elfies_per_user": int,
        "allowed_species_ids": list,
        "personality_presets_enabled": dict,
    },
    "engine": {
        "tick_interval_sec": (float, int),
    },
    "security": {
        "session_ttl_days": int,
        "rate_limit": dict,  # 嵌套字典额外校验
    },
}

# 深度嵌套字段的子校验
_NESTED_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "rate_limit": {
        "max_attempts": int,
        "window_seconds": int,
    },
}


def _validate_section_fields(section: str, data: Dict[str, Any]) -> None:
    """校验 PUT body 的字段类型与值范围，拒绝未知键。

    Raises:
        HTTPException 422: 包含非法键 / 类型不匹配 / 值域越界
    """
    schema = _SECTION_SCHEMAS.get(section, {})
    nested = _NESTED_SCHEMAS

    # 1. 拒绝未知键
    known_keys = set(schema.keys())
    for k in data:
        if k not in known_keys:
            raise HTTPException(
                status_code=422,
                detail=f"未知字段 '{k}'，{section} 允许的字段: {sorted(known_keys)}",
            )

    # 2. 类型 + 值域校验
    for k, v in data.items():
        expected = schema.get(k)
        if expected is None:
            continue  # 已在未知键检查中处理

        # 嵌套字典校验
        if isinstance(expected, type) and expected is dict and isinstance(v, dict):
            _validate_nested_dict(k, v, nested)
            continue

        # 类型校验（支持 tuple 多类型）
        if not isinstance(v, expected):
            type_names = (
                " 或 ".join(t.__name__ for t in expected)
                if isinstance(expected, tuple)
                else expected.__name__
            )
            raise HTTPException(
                status_code=422,
                detail=f"字段 '{k}' 类型应为 {type_names}，接收到 {type(v).__name__}",
            )

    # 3. 值域校验（特定字段）
    _validate_range(section, data)


def _validate_nested_dict(
    field_name: str, value: Dict[str, Any], nested_schemas: Dict[str, Any]
) -> None:
    """校验嵌套字典（如 rate_limit）的子字段。"""
    sub_schema = nested_schemas.get(field_name)
    if sub_schema is None:
        return

    for k, v in value.items():
        if k not in sub_schema:
            raise HTTPException(
                status_code=422,
                detail=f"未知字段 '{field_name}.{k}'",
            )
        expected_type = sub_schema[k]
        if not isinstance(v, expected_type):
            raise HTTPException(
                status_code=422,
                detail=f"字段 '{field_name}.{k}' 类型应为 {expected_type.__name__}，"
                f"接收到 {type(v).__name__}",
            )

    # 检查必填嵌套字段
    for k in sub_schema:
        if k not in value:
            raise HTTPException(
                status_code=422,
                detail=f"缺少必填字段 '{field_name}.{k}'",
            )


def _validate_range(section: str, data: Dict[str, Any]) -> None:
    """值域与业务规则校验。"""
    if section == "adoption":
        if "max_elfies_per_user" in data:
            if not 1 <= data["max_elfies_per_user"] <= MAX_ELFIES_PER_MACHINE:
                raise HTTPException(
                    422,
                    detail=f"max_elfies_per_user 应在 1 ~ {MAX_ELFIES_PER_MACHINE} 之间",
                )
        if "allowed_species_ids" in data:
            valid_types = {"dog", "fox"}
            if not data["allowed_species_ids"]:
                raise HTTPException(
                    422,
                    detail="allowed_species_ids 至少需要保留一个物种",
                )
            for t in data["allowed_species_ids"]:
                if t not in valid_types:
                    raise HTTPException(
                        422,
                        detail=f"allowed_species_ids 只允许 {sorted(valid_types)}，"
                        f"收到 '{t}'",
                    )

    elif section == "engine":
        if "tick_interval_sec" in data:
            if data["tick_interval_sec"] <= 0:
                raise HTTPException(422, detail="tick_interval_sec 应 > 0")
    elif section == "security":
        nested = data.get("rate_limit", {})
        if "max_attempts" in nested:
            if nested["max_attempts"] < 1:
                raise HTTPException(422, detail="rate_limit.max_attempts 应 ≥ 1")
        if "window_seconds" in nested:
            if nested["window_seconds"] < 1:
                raise HTTPException(422, detail="rate_limit.window_seconds 应 ≥ 1")
        if "session_ttl_days" in data:
            if data["session_ttl_days"] < 1:
                raise HTTPException(422, detail="session_ttl_days 应 ≥ 1")


# ---------------------------------------------------------------------------
# 工具：从文件读取 / 写入 system 子树
# ---------------------------------------------------------------------------


def _read_system_section(section: str) -> Dict[str, Any]:
    """从 ``configs/runtime.yaml`` 读取指定 section，与默认值深层合并后返回。"""
    return read_system_section(get_config_path(), section)


def _write_system_section(section: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """将 section 数据深层合并到 ``configs/runtime.yaml`` 并持久化。

    Returns:
        写入后的完整 section 字典（已合并默认值）。
    """
    result = write_system_section(get_config_path(), section, data)
    logger.info("System section '%s' updated", section)
    return result


# ===================================================================
# 路由：GET /api/owner/system/{section}
# ===================================================================


@router.get("/{section}")
async def get_system_section(
    section: str,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> Dict[str, Any]:
    """读取系统设置指定 section。

    返回深层合并默认值后的完整 section 字典。
    """
    _ = owner
    if section not in VALID_SECTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"无效的 section '{section}'，可用: {sorted(VALID_SECTIONS)}",
        )
    return _read_system_section(section)


# ===================================================================
# 路由：PUT /api/owner/system/{section}
# ===================================================================


@router.put("/{section}")
async def update_system_section(
    section: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> Dict[str, Any]:
    """更新系统设置指定 section。

    Body 为 section 子树的字段；未知键和类型不匹配返回 422。
    """
    _ = owner
    if section not in VALID_SECTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"无效的 section '{section}'，可用: {sorted(VALID_SECTIONS)}",
        )

    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="请求体必须是 JSON 对象")

    # 校验
    _validate_section_fields(section, body)

    # 持久化并返回更新后的完整 section
    result = _write_system_section(section, body)

    # 如果是 security section，清除 auth 缓存使新配置即时生效
    if section == "security":
        # The Accounts facade is process-scoped and owns its limiter cache.
        # Config itself is loaded from the authoritative file on every use.
        from app.interfaces.api.v1.auth import accounts_service  # noqa: PLC0415

        accounts_service(request).invalidate_security_cache()

    return result
