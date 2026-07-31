"""Resolve one Elfie's selected main food without crossing subscriptions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai_runtime.food.executor import NoAvailableFoodError
from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID, FoodPackage
from ai_runtime.food.store import FoodCatalog


@dataclass(frozen=True)
class MainFoodSelection:
    """The persisted main-food ID plus its authorization/health outcome."""

    food_id: str | None
    unavailable: bool = False


@dataclass(frozen=True)
class MainFoodRoute:
    """The one package eligible for role and same-food fallback execution."""

    food_id: str
    used_emergency: bool


def resolve_main_food(
    catalog: FoodCatalog,
    selection: MainFoodSelection,
    *,
    is_usable: Callable[[FoodPackage], bool],
) -> MainFoodRoute:
    """Choose selected/default food, then the global emergency package once."""
    if selection.unavailable:
        emergency = catalog.packages.get(FOOD_EMERGENCY_ID)
        if emergency is not None and is_usable(emergency):
            return MainFoodRoute(FOOD_EMERGENCY_ID, used_emergency=True)
        raise NoAvailableFoodError("no_available_food")

    primary_id = selection.food_id or FOOD_COMMON_ID
    primary = catalog.packages.get(primary_id)
    if primary is not None and is_usable(primary):
        return MainFoodRoute(primary_id, used_emergency=False)
    emergency = catalog.packages.get(FOOD_EMERGENCY_ID)
    if emergency is not None and is_usable(emergency):
        return MainFoodRoute(FOOD_EMERGENCY_ID, used_emergency=True)
    raise NoAvailableFoodError("no_available_food")


__all__ = ("MainFoodRoute", "MainFoodSelection", "resolve_main_food")
