"""The one Main-food setting exposed for each Elfie."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.food.elfie_policy import (
    DEFAULT_ALLOWED_FOODS,
    ElfieFoodPolicy,
)
from ai_runtime.food.models import FIXED_FOOD_KINDS
from app.features.accounts.auth import get_current_user
from app.infrastructure.persistence.elfie_repository import ElfieRecord, ElfieRepository

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


def _accessible_elfie(
    request: Request, elfie_id: str, user: Dict[str, Any]
) -> ElfieRecord:
    """Owner 可管理全巢粮食策略；普通用户仅可管理自己的精灵。"""
    repository = ElfieRepository(request.app.state.db_path)
    record = (
        repository.get(elfie_id)
        if user.get("role") == "owner"
        else repository.get_for_owner(elfie_id, owner_user_id=int(user["id"]))
    )
    if record is None:
        raise HTTPException(status_code=404, detail="精灵不存在或不属于您")
    return record


def _policy_from_record(record: ElfieRecord) -> ElfieFoodPolicy:
    if record.main_food is None or record.emergency_food is None:
        return ElfieFoodPolicy(record.elfie_id)
    allowed_set = {
        record.main_food,
        record.emergency_food,
        *record.other_foods,
    }
    allowed = tuple(key for key in FIXED_FOOD_KINDS if key in allowed_set)
    return ElfieFoodPolicy(
        elfie_id=record.elfie_id,
        default_food=record.main_food,
        allowed_foods=allowed or DEFAULT_ALLOWED_FOODS,
        fallback_food=record.emergency_food,
    )


@router.get("/")
async def get_food_policy(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    return _policy_from_record(_accessible_elfie(request, elfie_id, user)).to_dict()


@router.put("/")
async def update_food_policy(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    _accessible_elfie(request, elfie_id, user)
    policy = parse_food_policy_update(elfie_id, body)
    ElfieRepository(request.app.state.db_path).update_foods(
        elfie_id,
        main_food=policy.default_food,
        emergency_food=policy.fallback_food,
        other_foods=tuple(
            food
            for food in policy.allowed_foods
            if food not in {policy.default_food, policy.fallback_food}
        ),
    )
    return policy.to_dict()
