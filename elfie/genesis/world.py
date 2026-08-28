"""Typed semantic view of the bundled Elfaria World Canon.

The source document and YAML parsing live in Infrastructure.  These small
records are the domain boundary consumed by Genesis and deliberately contain
no paths, YAML objects, SQL rows or runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .contracts import KnowledgeLevel, MemoryCertainty

WorldItemStatus = Literal["active", "unknown-boundary"]


@dataclass(frozen=True)
class WorldKnowledgeFact:
    fact_id: str
    version: int
    statement: str
    scope: str
    topic: str
    aliases: tuple[str, ...]
    retrieval_terms: tuple[str, ...]
    level: KnowledgeLevel
    certainty: MemoryCertainty
    status: WorldItemStatus
    source_ref: str
    related_ids: tuple[str, ...]
    eligibility: tuple[str, ...]


@dataclass(frozen=True)
class WorldPlace:
    place_id: str
    version: int
    label: str
    kind: str
    parent_id: str
    aliases: tuple[str, ...]
    description: str
    status: WorldItemStatus


@dataclass(frozen=True)
class WorldStoryEvent:
    event_id: str
    version: int
    label: str
    summary: str
    temporal_label: str
    aliases: tuple[str, ...]
    source_ref: str


@dataclass(frozen=True)
class WorldCanonPackage:
    """The immutable, bounded public source used by one Genesis run."""

    version: int
    schema_version: int
    canon_version: str
    world_id: str
    display_name: str
    known_region_id: str
    known_region_name: str
    known_region_aliases: tuple[str, ...]
    civilization_relation_to_earth: str
    earth_arrival_statement: str
    earth_home_name: str
    earth_home_role: str
    places: tuple[WorldPlace, ...]
    story_events: tuple[WorldStoryEvent, ...]
    knowledge: tuple[WorldKnowledgeFact, ...]
    unknown_boundaries: tuple[str, ...]

    def place(self, place_id: str) -> WorldPlace:
        for place in self.places:
            if place.place_id == place_id:
                return place
        raise KeyError(place_id)

    def fact(self, fact_id: str) -> WorldKnowledgeFact:
        for fact in self.knowledge:
            if fact.fact_id == fact_id:
                return fact
        raise KeyError(fact_id)


__all__ = (
    "WorldCanonPackage",
    "WorldKnowledgeFact",
    "WorldPlace",
    "WorldStoryEvent",
    "WorldItemStatus",
)
