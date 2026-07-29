"""Resolve database food assignments against the external package catalog."""

from __future__ import annotations

from typing import Any

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
    granted.update(key for key in (catalog.default_food, catalog.fallback_food) if key)
    return tuple(key for key in catalog.recipes if key in granted)


def elfie_food_policy_projection(
    db_path: str,
    elfie_id: str,
    owner_user_id: int,
    catalog: FoodCatalog,
) -> dict[str, Any]:
    configured = get_elfie_primary_food(db_path, elfie_id)
    visible = visible_food_keys(db_path, owner_user_id, catalog)
    selected = (
        configured
        if configured in visible and configured in catalog.recipes
        else catalog.default_food
        if catalog.default_food in visible
        else visible[0]
        if visible
        else ""
    )
    return {
        "default_food": selected,
        "allowed_foods": list(visible),
        "fallback_food": (
            catalog.fallback_food if catalog.fallback_food in catalog.recipes else ""
        ),
        "configured_primary_food": configured,
        "primary_food_missing": bool(configured and configured not in catalog.recipes),
    }


def resolve_elfie_food_key(
    db_path: str,
    elfie_id: str,
    catalog: FoodCatalog,
) -> str | None:
    """Resolve one Elfie's current package without leaking DB facts to Runtime."""
    owner_user_id = get_elfie_owner_user_id(db_path, elfie_id)
    if owner_user_id is None:
        return catalog.default_food or next(iter(catalog.recipes), None)
    projection = elfie_food_policy_projection(
        db_path,
        elfie_id,
        owner_user_id,
        catalog,
    )
    selected = str(projection["default_food"])
    return selected or None
