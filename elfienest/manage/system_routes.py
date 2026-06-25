"""系统设置 REST API — 4 个 section 的 GET/PUT 端点。

使用方式::

    from .system_routes import router as system_router
    app.include_router(system_router)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from elfienest.config.runtime_store import read_system_section, write_system_section

from .admin_routes import require_admin

logger = logging.getLogger("elfienest.manage.system_routes")

router = APIRouter(prefix="/api/admin/system", tags=["system"])

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_RUNTIME_CONFIG_PATH: Path = _PROJECT_ROOT / "runtime" / "runtime_config.json"

# ---------------------------------------------------------------------------
# 可用的 section 白名单
# ---------------------------------------------------------------------------

VALID_SECTIONS = frozenset({"llm", "adoption", "engine", "security"})

# ---------------------------------------------------------------------------
# 各 section 字段类型期望（用于 PUT 校验）
# ---------------------------------------------------------------------------

# 内部辅助：校验嵌套字典（如 security.rate_limit）
_SECTION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "llm": {
        "default_cheap_model": str,
        "default_cheap_provider": str,
        "default_deep_model": str,
        "default_deep_provider": str,
        "default_multimodal_model": str,
        "default_multimodal_provider": str,
        "temperature": (float, int),
        "max_tokens": int,
        "energy_threshold_fast": (float, int),
        "complexity_threshold_deep": int,
    },
    "adoption": {
        "max_elfies_per_user": int,
        "allowed_anatomy_types": list,
        "personality_presets_enabled": dict,
    },
    "engine": {
        "tick_interval_sec": (float, int),
        "tts_enabled": bool,
        "max_elfies_per_room": (int, type(None)),
        "default_tts_voice": str,
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
    if section == "llm":
        if "temperature" in data:
            t = data["temperature"]
            if not (0.0 <= t <= 2.0):
                raise HTTPException(422, detail="temperature 应在 0.0 ~ 2.0 之间")
        if "max_tokens" in data:
            if data["max_tokens"] < 1:
                raise HTTPException(422, detail="max_tokens 应 ≥ 1")
        if "energy_threshold_fast" in data:
            if data["energy_threshold_fast"] < 0:
                raise HTTPException(422, detail="energy_threshold_fast 应 ≥ 0")
        if "complexity_threshold_deep" in data:
            if data["complexity_threshold_deep"] < 0:
                raise HTTPException(422, detail="complexity_threshold_deep 应 ≥ 0")

    elif section == "adoption":
        if "max_elfies_per_user" in data:
            if data["max_elfies_per_user"] < 1:
                raise HTTPException(
                    422, detail="max_elfies_per_user 应 ≥ 1"
                )
        if "allowed_anatomy_types" in data:
            valid_types = {"biped", "quadruped"}
            for t in data["allowed_anatomy_types"]:
                if t not in valid_types:
                    raise HTTPException(
                        422,
                        detail=f"allowed_anatomy_types 只允许 {sorted(valid_types)}，"
                        f"收到 '{t}'",
                    )

    elif section == "engine":
        if "tick_interval_sec" in data:
            if data["tick_interval_sec"] <= 0:
                raise HTTPException(422, detail="tick_interval_sec 应 > 0")
        if "max_elfies_per_room" in data:
            v = data["max_elfies_per_room"]
            if v is not None and v < 1:
                raise HTTPException(
                    422, detail="max_elfies_per_room 应 ≥ 1 或 null"
                )

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
    """从 ``runtime_config.json`` 读取指定 section，与默认值深层合并后返回。"""
    return read_system_section(_RUNTIME_CONFIG_PATH, section)


def _write_system_section(section: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """将 section 数据深层合并到 ``runtime_config.json`` 并持久化。

    Returns:
        写入后的完整 section 字典（已合并默认值）。
    """
    result = write_system_section(_RUNTIME_CONFIG_PATH, section, data)
    logger.info("System section '%s' updated", section)
    return result


# ===================================================================
# 路由：GET /api/admin/system/{section}
# ===================================================================


@router.get("/{section}")
async def get_system_section(
    section: str,
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """读取系统设置指定 section。

    返回深层合并默认值后的完整 section 字典。
    """
    _ = admin
    if section not in VALID_SECTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"无效的 section '{section}'，可用: {sorted(VALID_SECTIONS)}",
        )
    return _read_system_section(section)


# ===================================================================
# 路由：PUT /api/admin/system/{section}
# ===================================================================


@router.put("/{section}")
async def update_system_section(
    section: str,
    body: Dict[str, Any],
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    """更新系统设置指定 section。

    Body 为 section 子树的字段；未知键和类型不匹配返回 422。
    """
    _ = admin
    if section not in VALID_SECTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"无效的 section '{section}'，可用: {sorted(VALID_SECTIONS)}",
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=422, detail="请求体必须是 JSON 对象"
        )

    # 校验
    _validate_section_fields(section, body)

    # 持久化并返回更新后的完整 section
    result = _write_system_section(section, body)

    # 如果是 security section，清除 auth 缓存使新配置即时生效
    if section == "security":
        from .auth import (  # noqa: PLC0415
            invalidate_rate_limiter_cache,
            invalidate_session_cache,
        )

        invalidate_session_cache()
        invalidate_rate_limiter_cache()

    return result
