"""Typed creation-source contracts for one published Elfaria package.

The human world documents are upstream design material.  This module is the
only semantic boundary that a Genesis run consumes.  It deliberately keeps
technical package metadata, resident-facing facts and generator-only rules in
separate records so a compiler cannot accidentally hand hidden sampling data
to an Elfie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .contracts import KnowledgeLevel, MemoryCertainty

SourcePackageStatus = Literal["draft", "published", "retired"]
WorldItemStatus = Literal["active", "unknown-boundary"]
CoverageDisposition = Literal["mapped", "deferred", "excluded"]
KnowledgeEpistemicKind = Literal[
    "lived_observation",
    "taught",
    "documented",
    "hearsay",
    "myth",
    "unknown_boundary",
]


@dataclass(frozen=True)
class SourcePackageManifest:
    """Publication identity for the complete creation-source package."""

    package_id: str
    package_version: str
    schema_version: int
    status: SourcePackageStatus = "published"
    member_ids: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    content_sha256: str = ""


@dataclass(frozen=True)
class CoverageLink:
    """Bidirectional review link from an upstream fact to resident atoms."""

    upstream_id: str
    resident_fact_ids: tuple[str, ...] = ()
    disposition: CoverageDisposition = "mapped"
    rationale: str = ""


@dataclass(frozen=True)
class CoverageManifest:
    """Completeness map between the reviewed source documents and the package."""

    creator_source_ref: str
    resident_source_ref: str
    links: tuple[CoverageLink, ...] = ()


@dataclass(frozen=True)
class LifeArchetypeRule:
    """Generator-only household, learning and vocation archetype."""

    archetype_id: str
    species_ids: tuple[str, ...]
    life_stages: tuple[str, ...]
    place_ids: tuple[str, ...]
    weight: float
    household_roles: tuple[str, ...]
    care_and_trade_context: str
    learning_path_id: str
    institution_ids: tuple[str, ...]
    apprenticeship_ids: tuple[str, ...]
    vocation_id: str
    proficiency_band: str
    workplace_place_id: str = ""


@dataclass(frozen=True)
class RelationshipArchetype:
    """Generator-only social slot; never emitted as an archetype ID."""

    archetype_id: str
    role: str
    person_species_ids: tuple[str, ...]
    life_stages: tuple[str, ...]
    weight: float
    initial_trust: float
    importance: float
    familiarity: Literal["intimate", "known", "acquainted", "heard"] = "known"
    vocation_id: str = ""
    competency_ids: tuple[str, ...] = ()
    episode_theme_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EpisodeTheme:
    """Generator-only bounded skeleton for one personal episode."""

    theme_id: str
    label: str
    weight: float
    life_stages: tuple[str, ...]
    min_age_years: int
    required_roles: tuple[str, ...]
    place_kinds: tuple[str, ...]
    emotional_tone: str
    goal: str
    obstacle: str
    outcome: str
    impact: str
    required_knowledge_ids: tuple[str, ...] = ()
    required: bool = False
    order: int = 0


@dataclass(frozen=True)
class GenesisRoute:
    """Resident-visible route vocabulary, without geometry or path cost."""

    route_id: str
    from_place_id: str
    to_place_id: str
    label: str
    aliases: tuple[str, ...] = ()
    travel_time_band: str = "通常需要一段时间"
    access_conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpatialPopulationCell:
    """Generator-only birthplace choice; never emitted as resident knowledge."""

    cell_id: str
    place_id: str
    species_ids: tuple[str, ...]
    weight: float
    private_home_kind: str = "household"


@dataclass(frozen=True)
class SpatialPopulationModel:
    """Bounded historical sampling rules for pre-arrival life."""

    cells: tuple[SpatialPopulationCell, ...] = ()
    settlement_weights: tuple[tuple[str, float], ...] = ()

    def eligible_cells(self, species_id: str) -> tuple[SpatialPopulationCell, ...]:
        return tuple(cell for cell in self.cells if species_id in cell.species_ids)


@dataclass(frozen=True)
class NameRules:
    """Deterministic private-name pools used by Genesis."""

    default_names: tuple[str, ...] = ()
    species_names: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def pool(self, species_id: str) -> tuple[str, ...]:
        for key, values in self.species_names:
            if key == species_id and values:
                return values
        return self.default_names


@dataclass(frozen=True)
class GenerationPolicy:
    """Versioned structural limits and deterministic algorithm identifiers."""

    policy_version: str = "generation-policy.v1"
    seed_algorithm: str = "blake2b-labeled-v1"
    relationship_count: tuple[int, int] = (10, 20)
    episode_count: tuple[int, int] = (3, 5)
    salient_relationship_count: tuple[int, int] = (3, 5)
    repeated_relationship_count: tuple[int, int] = (1, 2)


@dataclass(frozen=True)
class EarthArrivalRules:
    """Eligibility and mandatory source-backed transition knowledge."""

    eligible_species_ids: tuple[str, ...] = ()
    eligible_life_stages: tuple[str, ...] = (
        "youth",
        "young_adult",
        "mature",
        "elder",
    )
    required_knowledge_ids: tuple[str, ...] = ()
    required_module_ids: tuple[str, ...] = ()

    def allows(self, species_id: str, life_stage: str) -> bool:
        return (
            not self.eligible_species_ids or species_id in self.eligible_species_ids
        ) and life_stage in self.eligible_life_stages


@dataclass(frozen=True)
class WorldKnowledgeFact:
    """One resident-facing source atom.

    The original v1 document supplies the first thirteen fields.  The
    remaining fields are optional publication metadata: absence means the
    compiler uses conservative defaults, never a hidden world fact.
    """

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
    importance: float = 0.5
    statement_variants: tuple[tuple[str, str], ...] = ()
    epistemic_kind: KnowledgeEpistemicKind = "documented"
    prerequisite_ids: tuple[str, ...] = ()
    acquisition_channels: tuple[str, ...] = ()
    exposure_weight: float = 0.5

    def variant(self, key: str) -> str | None:
        if key == "full":
            return self.statement
        for variant_id, value in self.statement_variants:
            if variant_id == key:
                return value
        return None


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
class GenesisSourcePackage:
    """The sole published, immutable source consumed by future Genesis runs."""

    version: int
    schema_version: int
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
    manifest: SourcePackageManifest
    routes: tuple[GenesisRoute, ...] = ()
    spatial_population: SpatialPopulationModel = field(
        default_factory=SpatialPopulationModel
    )
    name_rules: NameRules = field(default_factory=NameRules)
    generation_policy: GenerationPolicy = field(default_factory=GenerationPolicy)
    earth_arrival_rules: EarthArrivalRules = field(default_factory=EarthArrivalRules)
    coverage_manifest: CoverageManifest = field(
        default_factory=lambda: CoverageManifest("", "")
    )
    life_archetypes: tuple[LifeArchetypeRule, ...] = ()
    relationship_archetypes: tuple[RelationshipArchetype, ...] = ()
    episode_themes: tuple[EpisodeTheme, ...] = ()

    @property
    def package_version(self) -> str:
        return self.manifest.package_version

    @property
    def is_published(self) -> bool:
        return self.manifest.status == "published"

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

    def story_event(self, event_id: str) -> WorldStoryEvent:
        for event in self.story_events:
            if event.event_id == event_id:
                return event
        raise KeyError(event_id)


__all__ = (
    "CoverageDisposition",
    "CoverageLink",
    "CoverageManifest",
    "EarthArrivalRules",
    "EpisodeTheme",
    "GenesisRoute",
    "GenesisSourcePackage",
    "GenerationPolicy",
    "LifeArchetypeRule",
    "KnowledgeEpistemicKind",
    "NameRules",
    "RelationshipArchetype",
    "SourcePackageManifest",
    "SourcePackageStatus",
    "SpatialPopulationCell",
    "SpatialPopulationModel",
    "WorldItemStatus",
    "WorldKnowledgeFact",
    "WorldPlace",
    "WorldStoryEvent",
)
