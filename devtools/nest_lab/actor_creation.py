"""Creation choices from the shared Genesis species and age policy."""

from __future__ import annotations

from functools import lru_cache

from typing_extensions import TypedDict

from elfie.genesis import legal_candidate_age_range
from elfie.profile import get_species_definition
from infrastructure.persistence.configuration.world import load_genesis_source_package


class ActorSpecies(TypedDict):
    id: str
    label: str
    min_age: int
    max_age: int


@lru_cache(maxsize=1)
def actor_species() -> list[ActorSpecies]:
    """Expose supported actor age limits from the species authority."""
    items: list[ActorSpecies] = []
    policy = load_genesis_source_package().generation_policy
    for species in ("saevi", "tovren"):
        definition = get_species_definition(species, adoptable_only=True)
        if definition.genesis is None:
            raise ValueError(f"物种 {species} 缺少生成配置")
        ranges = [
            legal_candidate_age_range(definition.genesis, stage, policy)
            for stage in ("youth", "young_adult", "mature", "elder")
        ]
        ranges = [(low, high) for low, high in ranges if low <= high]
        items.append(
            {
                "id": species,
                "label": definition.display_name_zh,
                "min_age": max(2, min(low for low, _ in ranges)),
                "max_age": max(high for _, high in ranges),
            }
        )
    return items
