"""Owner food-access routes backed by canonical account projections."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from ai_runtime.food.models import SYSTEM_FOOD_IDS
from ai_runtime.food.store import FoodCatalogStore
from app.features.accounts.auth import AuthenticatedUser, require_manager
from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.food_assignments import (
    list_food_access_users,
    replace_food_access_users,
)
from app.infrastructure.persistence.store import get_db
from app.interfaces.api.food_catalog_support import require_package

router = APIRouter()


class FoodVisibilityUser(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: int
    account_id: str
    display_name: Optional[str]
    assigned: bool


class FoodVisibilityView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    food_key: str
    global_: bool = Field(alias="global")
    user_ids: list[int]
    users: list[FoodVisibilityUser]


class FoodVisibilityUpdateRequest(BaseModel):
    """Strict Owner request for replacing food visibility assignments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_ids: list[StrictInt]


class FoodVisibilityUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    food_key: str
    user_ids: list[int]


@router.get("/{food_id}/visibility")
async def get_food_visibility(
    food_id: str,
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> FoodVisibilityView:
    _ = owner
    require_package(FoodCatalogStore().load(), food_id)
    system = food_id in SYSTEM_FOOD_IDS
    assigned = (
        set()
        if system
        else set(list_food_access_users(request.app.state.db_path, food_id))
    )
    with get_db(request.app.state.db_path) as connection:
        users = AccountRepository(connection).list_non_owner_users()
    return FoodVisibilityView.model_validate(
        {
            "food_key": food_id,
            "global": system,
            "user_ids": [] if system else sorted(assigned),
            "users": [
                FoodVisibilityUser(
                    user_id=row.user_id,
                    account_id=row.account_id,
                    display_name=row.display_name,
                    assigned=system or row.user_id in assigned,
                )
                for row in users
            ],
        }
    )


@router.put("/{food_id}/visibility")
async def edit_food_visibility(
    food_id: str,
    body: FoodVisibilityUpdateRequest,
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> FoodVisibilityUpdateResponse:
    _ = owner
    require_package(FoodCatalogStore().load(), food_id)
    if food_id in SYSTEM_FOOD_IDS:
        raise HTTPException(status_code=409, detail="系统粮食始终对所有用户可见")
    assigned = replace_food_access_users(
        request.app.state.db_path,
        food_id,
        body.user_ids,
    )
    return FoodVisibilityUpdateResponse(food_key=food_id, user_ids=list(assigned))


__all__ = ("router",)
