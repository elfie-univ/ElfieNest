"""Elfie 路由配置 REST API — 每精灵模型路由管理。

用户端点，通过 get_current_user + 所有权验证保护。
每个精灵独立配置场景模型路由（idle/deep/vision/tool_use/sleep）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from elfienest.manage.store import get_db
from runtime.model_route import (
    SCENE_SLOTS,
    SceneRoute,
    load_model_route,
    save_model_route,
)

from .user_routes import get_current_user

logger = logging.getLogger("elfienest.manage.route_routes")

router = APIRouter(prefix="/api/user/elfies/{elfie_id}/route", tags=["routes"])


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _check_ownership(conn, elfie_id: str, user_id: int) -> bool:
    """检查精灵所有权。"""
    cur = conn.execute(
        "SELECT owner_user_id FROM elfie_registry WHERE elfie_id=?",
        (elfie_id,),
    )
    row = cur.fetchone()
    return row is not None and row[0] == user_id


def _validate_scene_routes(scene_routes: Dict[str, Any]) -> None:
    """验证场景路由配置的有效性。"""
    if not isinstance(scene_routes, dict):
        raise HTTPException(status_code=422, detail="scene_routes 必须为字典")

    for scene, route_data in scene_routes.items():
        if scene not in SCENE_SLOTS:
            raise HTTPException(
                status_code=422,
                detail=f"未知场景 '{scene}'，有效场景: {SCENE_SLOTS}",
            )

        if not isinstance(route_data, dict):
            raise HTTPException(
                status_code=422,
                detail=f"场景 '{scene}' 的路由配置必须为字典",
            )

        # 验证 primary 字段
        if "primary" not in route_data:
            raise HTTPException(
                status_code=422,
                detail=f"场景 '{scene}' 缺少 primary 字段",
            )

        # 验证 fallbacks 字段（可选）
        if "fallbacks" in route_data:
            if not isinstance(route_data["fallbacks"], list):
                raise HTTPException(
                    status_code=422,
                    detail=f"场景 '{scene}' 的 fallbacks 必须为列表",
                )

        # 验证 energy_threshold 字段（可选）
        if "energy_threshold" in route_data:
            threshold = route_data["energy_threshold"]
            if not isinstance(threshold, (int, float)) or not (0 <= threshold <= 100):
                raise HTTPException(
                    status_code=422,
                    detail=f"场景 '{scene}' 的 energy_threshold 必须为 0-100 的数值",
                )


# ===================================================================
# 路由：GET /api/user/elfies/{elfie_id}/route
# ===================================================================


@router.get("/")
async def get_elfie_route(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """读取精灵的模型路由配置。

    如果精灵没有自定义路由配置，返回系统默认配置。
    """
    db = request.app.state.db_path

    with get_db(db) as conn:
        if not _check_ownership(conn, elfie_id, user["id"]):
            raise HTTPException(status_code=404, detail="精灵不存在或不属于您")

    # 加载路由配置
    route = load_model_route(elfie_id)

    return route.to_dict()


# ===================================================================
# 路由：PUT /api/user/elfies/{elfie_id}/route
# ===================================================================


@router.put("/")
async def update_elfie_route(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """更新精灵的模型路由配置。

    Body: {"scene_routes": {"idle": {"primary": "ollama/qwen3.5:0.8b", ...}, ...}}
    """
    db = request.app.state.db_path

    with get_db(db) as conn:
        if not _check_ownership(conn, elfie_id, user["id"]):
            raise HTTPException(status_code=404, detail="精灵不存在或不属于您")

    # 验证请求体
    if "scene_routes" not in body:
        raise HTTPException(status_code=422, detail="缺少 scene_routes 字段")

    scene_routes_data = body["scene_routes"]
    _validate_scene_routes(scene_routes_data)

    # 构建路由配置
    route = load_model_route(elfie_id)  # 加载现有配置作为基础

    # 更新场景路由
    for scene, route_data in scene_routes_data.items():
        route.scene_routes[scene] = SceneRoute(
            primary=route_data["primary"],
            fallbacks=route_data.get("fallbacks", []),
            energy_threshold=route_data.get("energy_threshold", 0.0),
        )

    # 保存
    save_model_route(route)

    logger.info(
        "用户 '%s' 更新了精灵 '%s' 的路由配置",
        user["username"],
        elfie_id,
    )

    return route.to_dict()
