"""Compose Runtime food selection with the final Nest repository."""

from __future__ import annotations

from collections.abc import Callable

from ai_runtime.food.elfie_policy import ElfieFoodPolicy
from app.infrastructure.persistence.elfie_repository import ElfieRepository


def final_food_policy_loader(db_path: str) -> Callable[[str], ElfieFoodPolicy]:
    repository = ElfieRepository(db_path)

    def load(elfie_id: str) -> ElfieFoodPolicy:
        record = repository.get(elfie_id)
        if record is None:
            return ElfieFoodPolicy(elfie_id)
        allowed = tuple(
            dict.fromkeys(
                food
                for food in (
                    record.main_food,
                    record.emergency_food,
                    *record.other_foods,
                )
                if food
            )
        )
        if not allowed:
            return ElfieFoodPolicy(elfie_id)
        return ElfieFoodPolicy.from_dict(
            elfie_id,
            {
                "default_food": record.main_food or allowed[0],
                "fallback_food": record.emergency_food or allowed[0],
                "allowed_foods": allowed,
            },
        )

    return load


__all__ = ("final_food_policy_loader",)
