"""The one Main-food setting exposed for each Elfie."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.food.store import FoodCatalogStore
from app.features.accounts.auth import get_current_user
from app.features.configuration.food_access import elfie_food_policy_projection
from app.infrastructure.persistence.food_assignments import set_elfie_primary_food
from app.infrastructure.persistence.store import get_db

router = APIRouter(
    prefix="/api/user/elfies/{elfie_id}/food-policy",
    tags=["food-policy"],
)


def _accessible_elfie(
    request: Request, elfie_id: str, user: Dict[str, Any]
) -> Dict[str, Any]:
    query = "SELECT owner_user_id FROM elfie_registry WHERE elfie_id=?"
    parameters: tuple[object, ...] = (elfie_id,)
    if user.get("role") != "owner":
        query += " AND owner_user_id=?"
        parameters = (elfie_id, user["id"])
    with get_db(request.app.state.db_path) as connection:
        row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在或不属于您")
    return dict(row)


@router.get("/")
async def get_food_policy(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    elfie = _accessible_elfie(request, elfie_id, user)
    return elfie_food_policy_projection(
        request.app.state.db_path,
        elfie_id,
        int(elfie["owner_user_id"]),
        FoodCatalogStore().load(),
    )


@router.put("/")
async def update_food_policy(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    elfie = _accessible_elfie(request, elfie_id, user)
    catalog = FoodCatalogStore().load()
    current = elfie_food_policy_projection(
        request.app.state.db_path,
        elfie_id,
        int(elfie["owner_user_id"]),
        catalog,
    )
    food_id = str(body.get("main_food_id") or "").strip()
    if food_id not in {
        str(item["food_id"]) for item in current["main_food_options"]
    }:
        raise HTTPException(status_code=422, detail="所选主粮当前不可用或未授权")
    set_elfie_primary_food(request.app.state.db_path, elfie_id, food_id)
    return elfie_food_policy_projection(
        request.app.state.db_path,
        elfie_id,
        int(elfie["owner_user_id"]),
        catalog,
    )
