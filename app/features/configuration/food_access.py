"""Resolve user-visible primary food from Nest DB and Runtime facts."""

from __future__ import annotations

from typing import Any

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.health import project_food_health
from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from ai_runtime.food.store import FoodCatalog
from app.infrastructure.persistence.food_assignments import (
    get_elfie_owner_user_id,
    get_elfie_primary_food,
    list_user_food_access,
)


def visible_food_keys(
    db_path: str,
    user_id: int,
    catalog: FoodCatalog,
) -> tuple[str, ...]:
    granted = set(list_user_food_access(db_path, user_id))
    granted.add(FOOD_COMMON_ID)
    return tuple(
        package.key
        for package in catalog.ordered_packages()
        if package.key != FOOD_EMERGENCY_ID
        and package.key in granted
        and not package.archived
    )


def elfie_food_policy_projection(
    db_path: str,
    elfie_id: str,
    owner_user_id: int,
    catalog: FoodCatalog,
) -> dict[str, Any]:
    evidence = ModelEvidenceStore().load()
    configured = get_elfie_primary_food(db_path, elfie_id)
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
