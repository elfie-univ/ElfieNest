"""Compose Runtime main-food selection with the final Nest repository."""

from __future__ import annotations

from collections.abc import Callable

from ai_runtime.food.resolver import MainFoodSelection
from ai_runtime.food.store import FoodCatalogRepository
from app.features.configuration.food_access import resolve_elfie_main_food_selection


def final_main_food_loader(
    db_path: str,
    food_catalog_repository: FoodCatalogRepository,
) -> Callable[[str], MainFoodSelection]:
    def load(elfie_id: str) -> MainFoodSelection:
        return resolve_elfie_main_food_selection(
            db_path,
            elfie_id,
            food_catalog_repository.load(),
        )

    return load


__all__ = ("final_main_food_loader",)
