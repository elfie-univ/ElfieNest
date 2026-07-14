"""旧精灵路由 API 的粮食策略兼容入口。

精灵不再直接选择 Provider/模型；新客户端应使用 ``/food-policy``。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from elfienest.persistence.store import get_db
from runtime.food.elfie_policy import (
    load_elfie_food_policy,
    save_elfie_food_policy,
)

from .food_policy_routes import parse_food_policy_update
from .user_routes import get_current_user

logger = logging.getLogger("elfienest.api.route_routes")

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


def _get_owned_config_dir(conn, elfie_id: str, user_id: int) -> str:
    cur = conn.execute(
        "SELECT config_dir FROM elfie_registry WHERE elfie_id=? AND owner_user_id=?",
        (elfie_id, user_id),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在或不属于您")
    return row["config_dir"]


# ===================================================================
# 路由：GET /api/user/elfies/{elfie_id}/route
# ===================================================================


@router.get("/")
async def get_elfie_route(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """兼容读取粮食权限，不再返回任何模型引用。"""
    db = request.app.state.db_path

    with get_db(db) as conn:
        config_dir = _get_owned_config_dir(conn, elfie_id, user["id"])

    payload = load_elfie_food_policy(elfie_id, config_dir).to_dict()
    payload.update(
        {
            "deprecated": True,
            "replacement": f"/api/user/elfies/{elfie_id}/food-policy",
        }
    )
    return payload


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
    """兼容更新粮食权限；明确拒绝旧的直接模型路由结构。"""
    db = request.app.state.db_path

    with get_db(db) as conn:
        config_dir = _get_owned_config_dir(conn, elfie_id, user["id"])

    if "scene_routes" in body:
        raise HTTPException(
            status_code=410,
            detail="模型路由配置已停用；请改为配置 default_food、allowed_foods 和 fallback_food",
        )
    policy = parse_food_policy_update(elfie_id, body)
    save_elfie_food_policy(policy, config_dir)

    logger.info(
        "用户 '%s' 通过旧路由入口更新了精灵 '%s' 的粮食权限",
        user["username"],
        elfie_id,
    )

    payload = policy.to_dict()
    payload["deprecated"] = True
    payload["replacement"] = f"/api/user/elfies/{elfie_id}/food-policy"
    return payload
