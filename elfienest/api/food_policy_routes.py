"""每精灵粮食偏好和允许范围 API。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from elfienest.persistence.store import get_db
from runtime.food.elfie_policy import (
    ElfieFoodPolicy,
    load_elfie_food_policy,
    save_elfie_food_policy,
)
from runtime.food.models import FIXED_FOOD_KINDS

from .user_routes import get_current_user

router = APIRouter(
    prefix="/api/user/elfies/{elfie_id}/food-policy",
    tags=["food-policy"],
)


def parse_food_policy_update(elfie_id: str, body: Dict[str, Any]) -> ElfieFoodPolicy:
    allowed = body.get("allowed_foods")
    if not isinstance(allowed, list) or not allowed:
        raise HTTPException(status_code=422, detail="allowed_foods 必须是非空数组")
    unknown = [item for item in allowed if item not in FIXED_FOOD_KINDS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知粮食: {unknown}")
    default_food = str(body.get("default_food", ""))
    fallback_food = str(body.get("fallback_food", ""))
    if default_food not in allowed or fallback_food not in allowed:
        raise HTTPException(
            status_code=422,
            detail="default_food 和 fallback_food 必须包含在 allowed_foods 中",
        )
    return ElfieFoodPolicy(
        elfie_id=elfie_id,
        default_food=default_food,
        allowed_foods=tuple(allowed),
        fallback_food=fallback_food,
    )


def _owned_config_dir(request: Request, elfie_id: str, user_id: int) -> str:
    with get_db(request.app.state.db_path) as conn:
        row = conn.execute(
            "SELECT config_dir FROM elfie_registry WHERE elfie_id=? AND owner_user_id=?",
            (elfie_id, user_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在或不属于您")
    return str(row["config_dir"])


@router.get("/")
async def get_food_policy(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    config_dir = _owned_config_dir(request, elfie_id, user["id"])
    return load_elfie_food_policy(elfie_id, config_dir).to_dict()


@router.put("/")
async def update_food_policy(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    config_dir = _owned_config_dir(request, elfie_id, user["id"])
    policy = parse_food_policy_update(elfie_id, body)
    save_elfie_food_policy(policy, config_dir)
    return policy.to_dict()
