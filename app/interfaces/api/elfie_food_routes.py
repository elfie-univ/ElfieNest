"""The one Main-food setting exposed for each Elfie."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.features.accounts.auth import get_current_user
from app.features.configuration.food_access import elfie_food_policy_projection
from app.infrastructure.persistence.elfie_repository import ElfieRecord, ElfieRepository
from app.infrastructure.persistence.food_assignments import set_elfie_main_food_id
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository

router = APIRouter(
    prefix="/api/user/elfies/{elfie_id}/food-policy",
    tags=["elfie-food"],
)


def _accessible_elfie(
    request: Request, elfie_id: str, user: Dict[str, Any]
) -> ElfieRecord:
    repository = ElfieRepository(request.app.state.db_path)
    record = (
        repository.get(elfie_id)
        if user.get("role") in {"owner", "admin"}
        else repository.get_for_owner(elfie_id, owner_user_id=user["user_id"])
    )
    if record is None:
        raise HTTPException(status_code=404, detail="精灵不存在或不属于您")
    return record


def _projection(request: Request, record: ElfieRecord) -> Dict[str, Any]:
    return elfie_food_policy_projection(
        request.app.state.db_path,
        record.elfie_id,
        record.owner_user_id,
        SQLiteFoodPackageRepository(request.app.state.db_path).load(),
    )


@router.get("/")
async def get_elfie_main_food(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    return _projection(request, _accessible_elfie(request, elfie_id, user))


@router.put("/")
async def update_elfie_main_food(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    record = _accessible_elfie(request, elfie_id, user)
    main_food_id = body.get("main_food_id")
    if set(body) != {"main_food_id"} or not isinstance(main_food_id, str):
        raise HTTPException(status_code=422, detail="只接受 main_food_id")
    selected = main_food_id.strip()
    projection = _projection(request, record)
    option_ids = {item["food_id"] for item in projection["main_food_options"]}
    if selected not in option_ids:
        raise HTTPException(status_code=422, detail="主粮不可选择")
    set_elfie_main_food_id(request.app.state.db_path, record.elfie_id, selected)
    return _projection(request, record)
