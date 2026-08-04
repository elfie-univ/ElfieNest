"""Resolve user-visible primary food from Nest DB and Runtime facts."""

from __future__ import annotations

from typing import Any

from ai_runtime.food.evidence import query_model_evidence
from ai_runtime.food.health import project_food_health
from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from ai_runtime.food.resolver import MainFoodSelection
from ai_runtime.food.store import FoodCatalog
from app.infrastructure.persistence.food_assignments import (
    get_elfie_main_food_id,
    get_elfie_owner_user_id,
)


def visible_food_keys(
    db_path: str,
    user_id: int,
    catalog: FoodCatalog,
) -> tuple[str, ...]:
    return tuple(
        package.key
        for package in catalog.ordered_packages()
        if package.key != FOOD_EMERGENCY_ID
        and not package.archived
        and (
            package.visibility_mode == "global"
            or user_id in package.visible_user_ids
        )
    )


def elfie_food_policy_projection(
    db_path: str,
    elfie_id: str,
    owner_user_id: int,
    catalog: FoodCatalog,
) -> dict[str, Any]:
    evidence = query_model_evidence()
    configured = get_elfie_main_food_id(db_path, elfie_id)
    visible = visible_food_keys(db_path, owner_user_id, catalog)
    options = [
        {
            "food_id": key,
            "display_name": catalog.packages[key].display_name,
        }
        for key in visible
        if catalog.packages[key].enabled
        and project_food_health(catalog.packages[key], evidence).status
        in {"healthy", "degraded"}
    ]
    option_ids = {item["food_id"] for item in options}
    effective = (
        configured
        if configured in option_ids
        else FOOD_COMMON_ID
        if not configured and FOOD_COMMON_ID in option_ids
        else ""
    )
    return {
        "main_food_id": configured or "",
        "effective_main_food_id": effective,
        "main_food_options": options,
        "main_food_unavailable": bool(configured and configured not in option_ids),
    }


def resolve_elfie_food_key(
    db_path: str,
    elfie_id: str,
    catalog: FoodCatalog,
) -> str | None:
    owner_user_id = get_elfie_owner_user_id(db_path, elfie_id)
    if owner_user_id is None:
        return None
    projection = elfie_food_policy_projection(
        db_path,
        elfie_id,
        owner_user_id,
        catalog,
    )
    selected = str(projection["effective_main_food_id"])
    return selected or str(projection["main_food_id"]) or None


def resolve_elfie_main_food_selection(
    db_path: str,
    elfie_id: str,
    catalog: FoodCatalog,
) -> MainFoodSelection:
    owner_user_id = get_elfie_owner_user_id(db_path, elfie_id)
    if owner_user_id is None:
        return MainFoodSelection(None, unavailable=True)
    projection = elfie_food_policy_projection(
        db_path,
        elfie_id,
        owner_user_id,
        catalog,
    )
    configured = str(projection["main_food_id"]) or None
    return MainFoodSelection(
        configured,
        unavailable=bool(projection["main_food_unavailable"]),
    )
