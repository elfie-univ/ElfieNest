"""Production composition for the Food configuration boundary."""

from __future__ import annotations

from app.features.configuration.food import FoodService
from infrastructure.models import RuntimeFoodTechnologyAdapter
from infrastructure.persistence import SQLiteFoodAdapter


def build_food_service(db_path: str) -> FoodService:
    persistence = SQLiteFoodAdapter(db_path)
    return FoodService(
        catalog=persistence,
        technology=RuntimeFoodTechnologyAdapter(),
        assignments=persistence,
    )


__all__ = ("build_food_service",)
