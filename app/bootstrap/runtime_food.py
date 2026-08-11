"""Compose Runtime main-food selection with the final Nest repository."""

from __future__ import annotations

from collections.abc import Callable

from app.features.configuration.food import FoodService, ResolveElfieFoodQuery
from elfie.brain.food_port import MainFoodSelection


def final_main_food_loader(
    food_service: FoodService,
) -> Callable[[str], MainFoodSelection]:
    def load(elfie_id: str) -> MainFoodSelection:
        result = food_service.resolve_elfie_food(
            ResolveElfieFoodQuery(elfie_id=elfie_id)
        )
        return MainFoodSelection(result.food_id, unavailable=result.unavailable)

    return load


__all__ = ("final_main_food_loader",)
