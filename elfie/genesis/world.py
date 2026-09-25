"""Typed creation-source contracts for one published Elfaria package.

The human world documents are upstream design material.  This module is the
only semantic boundary that a Genesis run consumes.  It deliberately keeps
technical package metadata, resident-facing facts and generator-only rules in
separate records so a compiler cannot accidentally hand hidden sampling data
to an Elfie.
"""

from __future__ import annotations

import math
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
class GeographyNetwork:
    """Typed runtime view of the reviewed geography topology.

    The source package keeps the grid and reviewed backbone paths as creation
    inputs.  They are not resident-facing coordinates.  Genesis uses this
    view only to prove that a selected journey is legal and to calculate the
    configured local-day cost.
    """

    region_matrix: tuple[tuple[str, ...], ...] = ()
    land_backbone_paths: tuple[tuple[str, ...], ...] = ()
    water_grid_hop_edges: tuple[tuple[str, str, int], ...] = ()
    island_destinations: tuple[tuple[str, str, str, int], ...] = ()
    ferry_nodes: tuple[str, ...] = ()
    place_cells: tuple[tuple[str, str], ...] = ()
    land_days_per_grid_hop: int = 2
    water_days_per_grid_hop: int = 3
    days_per_local_year: int = 196

    def __post_init__(self) -> None:
        if self.days_per_local_year < 1:
            raise ValueError("geography calendar days_per_local_year must be positive")

    @property
    def _land_edges(self) -> frozenset[tuple[str, str]]:
        edges: set[tuple[str, str]] = set()
        for path in self.land_backbone_paths:
            for left, right in zip(path, path[1:]):
                edges.add(_ordered_edge(left, right))
        for row, values in enumerate(self.region_matrix):
            for column, region in enumerate(values):
                if region in {"E", "X"}:
                    continue
                for next_row, next_column in (
                    (row + 1, column),
                    (row, column + 1),
                ):
                    if next_row >= len(self.region_matrix):
                        continue
                    if next_column >= len(self.region_matrix[next_row]):
                        continue
                    if self.region_matrix[next_row][next_column] != region:
                        continue
                    edges.add(
                        _ordered_edge(
                            _cell_label(row, column),
                            _cell_label(next_row, next_column),
                        )
                    )
        return frozenset(edges)

    def cell_for_place(self, place_id: str) -> str | None:
        return dict(self.place_cells).get(place_id)

    def shortest_land_path(
        self, start: str, destination: str
    ) -> tuple[str, ...] | None:
        """Return the deterministic shortest legal land path, if one exists."""

        if not start or not destination:
            return None
        if start == destination:
            return (start,)
        adjacency: dict[str, set[str]] = {}
        for left, right in self._land_edges:
            adjacency.setdefault(left, set()).add(right)
            adjacency.setdefault(right, set()).add(left)
        frontier: list[tuple[str, tuple[str, ...]]] = [(start, (start,))]
        visited = {start}
        for cell, path in frontier:
            for neighbor in sorted(adjacency.get(cell, ())):
                if neighbor in visited:
                    continue
                next_path = (*path, neighbor)
                if neighbor == destination:
                    return next_path
                visited.add(neighbor)
                frontier.append((neighbor, next_path))
        return None


@dataclass(frozen=True)
class GeographyAccessRule:
    """A source-declared permission boundary for one public place."""

    rule_id: str
    place_id: str
    requires: tuple[str, ...] = ()
    ordinary_travel_allowed: bool = True
    observation_only: bool = False
    landing_is_island: bool = False


def _ordered_edge(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _cell_label(row: int, column: int) -> str:
    return f"R{row}C{column}"


@dataclass(frozen=True)
class SpatialPopulationCell:
    """Generator-only birthplace choice; never emitted as resident knowledge."""

    cell_id: str
    region_id: str
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
class VisitOpportunityRule:
    """One bounded, source-configured opportunity for a personal visit."""

    opportunity_id: str
    place_ids: tuple[str, ...]
    base_visit_probability: float
    home_regions: tuple[str, ...] = ()
    base_visit_probabilities_by_region: tuple[tuple[str, float], ...] = ()
    minimum_age_years: int = 2
    purpose: str = "sightseeing"
    stay_days: int = 1
    max_repeat_count: int = 1
    member_probability: float = 1.0
    member_probabilities: tuple[tuple[str, float], ...] = ()
    purpose_weights: tuple[tuple[str, float], ...] = ()
    personality_factor_by_purpose: tuple[tuple[str, str], ...] = ()
    species_multipliers: tuple[tuple[str, float], ...] = ()
    region_multipliers: tuple[tuple[str, float], ...] = ()
    requires_opportunity_id: str = ""
    distance_decay_days: float = 12.0

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip() or not self.place_ids:
            raise ValueError("visit opportunity must have an id and places")
        if (
            not math.isfinite(self.base_visit_probability)
            or not 0.0 <= self.base_visit_probability <= 1.0
        ):
            raise ValueError("visit opportunity base probability must be in [0, 1]")
        if (
            self.minimum_age_years < 0
            or self.stay_days < 1
            or self.max_repeat_count < 1
        ):
            raise ValueError(
                "visit opportunity age, stay and repeat limits are invalid"
            )
        for _, probability in (*self.member_probabilities,):
            if not 0.0 <= probability <= 1.0:
                raise ValueError("visit opportunity member probability is invalid")
        for purpose, weight in self.purpose_weights:
            if not purpose.strip() or weight < 0.0:
                raise ValueError("visit opportunity purpose weight is invalid")
        for _, probability in self.base_visit_probabilities_by_region:
            if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise ValueError("visit opportunity regional probability is invalid")
        if any(
            not purpose.strip() or factor not in {"social", "curiosity", "risk"}
            for purpose, factor in self.personality_factor_by_purpose
        ):
            raise ValueError("visit opportunity personality factor is invalid")
        if self.purpose_weights and not any(
            weight > 0.0 for _, weight in self.purpose_weights
        ):
            raise ValueError("visit opportunity purpose weights cannot all be zero")
        for _, multiplier in (
            *self.species_multipliers,
            *self.region_multipliers,
        ):
            if multiplier < 0.0:
                raise ValueError("visit opportunity multiplier must not be negative")
        if self.distance_decay_days <= 0.0:
            raise ValueError("visit opportunity distance decay must be positive")

    def member_probability_for(self, place_id: str) -> float:
        return dict(self.member_probabilities).get(place_id, self.member_probability)

    def purpose_options(self) -> tuple[tuple[str, float], ...]:
        """Return configured purpose shares, with the legacy purpose as fallback."""

        return self.purpose_weights or ((self.purpose, 1.0),)

    def base_visit_probability_for(self, region_id: str) -> float:
        """Return the reviewed base visit probability for one home region."""

        return dict(self.base_visit_probabilities_by_region).get(
            region_id, self.base_visit_probability
        )

    def personality_factor_for(self, purpose: str) -> str:
        """Return the single personality axis that governs this purpose."""

        return dict(self.personality_factor_by_purpose).get(purpose, "curiosity")

    def species_multiplier_for(self, species_id: str) -> float:
        return dict(self.species_multipliers).get(species_id, 1.0)

    def region_multiplier_for(self, region_id: str) -> float:
        return dict(self.region_multipliers).get(region_id, 1.0)


@dataclass(frozen=True)
class GenerationPolicy:
    """Versioned structural limits and deterministic algorithm identifiers."""

    policy_version: str = "generation-policy.v1"
    seed_algorithm: str = "blake2b-labeled-v1"
    normal_episode_minimum: int = 5
    medium_knowledge_probability: float = 0.5
    candidate_proposal_count: int = 96
    candidate_options_per_choice: int = 8
    candidate_total_backtracks: int = 64
    candidate_minimum_age_years: int = 2
    candidate_age_reserve_years: int = 4
    candidate_stage_weights: tuple[tuple[str, float], ...] = (
        ("youth", 0.0),
        ("young_adult", 0.75),
        ("mature", 0.20),
        ("elder", 0.05),
    )
    family_child_count_distribution: tuple[tuple[int, float], ...] = (
        (1, 0.40),
        (2, 0.45),
        (3, 0.15),
    )
    family_parent_min_age_gap_years: int = 3
    family_partner_min_age_years: int = 3
    family_partner_annual_probability: float = 0.25
    family_max_children: int = 3
    family_lifespan_cdf_power: int = 6
    family_lifespan_sampler_version: str = "conditioned-lifespan-cdf.v1"
    relationship_importance_baselines: tuple[tuple[str, float], ...] = (
        ("core", 0.75),
        ("sibling", 0.65),
        ("friend", 0.35),
        ("teacher", 0.45),
        ("direct_acquaintance", 0.25),
    )
    relationship_layer_decay_lambda: float = 0.9
    friend_layer_decay_lambda: float = 0.65
    friend_contact_beta: float = 0.8
    friend_max_count: int = 2
    visit_sampler_version: str = "visits-zero-heavy-power-count.v1"
    visit_repeat_count_power: float = 23.0
    visit_social_multiplier_base: float = 0.8
    visit_social_multiplier_slope: float = 0.4
    visit_curiosity_multiplier_base: float = 0.8
    visit_curiosity_multiplier_slope: float = 0.4
    visit_risk_multiplier_base: float = 0.8
    visit_risk_openness_slope: float = 0.4
    visit_risk_neuroticism_slope: float = -0.2
    visit_cross_region_lifetime_fraction: float = 0.1
    visit_opportunities: tuple[VisitOpportunityRule, ...] = ()

    def candidate_stage_weight(self, stage: str) -> float:
        """Return the configured default-selection weight for one life stage."""

        return dict(self.candidate_stage_weights).get(stage, 0.0)

    def relationship_importance(self, role: str, fallback: float) -> float:
        """Return the configured baseline for a relationship role."""

        key = (
            "core"
            if role in {"parent", "partner", "child"}
            else role
            if role in {"sibling", "friend", "teacher"}
            else "direct_acquaintance"
        )
        return dict(self.relationship_importance_baselines).get(key, fallback)


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
    post_arrival_knowledge_ids: tuple[str, ...] = ()
    preparation_duration_local_days: int = 3

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
    mastery_difficulty: str = ""
    conditions: tuple[KnowledgeCondition, ...] = ()

    def variant(self, key: str) -> str | None:
        if key == "full":
            return self.statement
        for variant_id, value in self.statement_variants:
            if variant_id == key:
                return value
        return None


@dataclass(frozen=True)
class KnowledgeCondition:
    """One source-declared condition for acquiring a resident knowledge unit."""

    kind: Literal["place", "route", "experience", "vocation"]
    attributes: tuple[tuple[str, str], ...]

    def value(self, key: str) -> str:
        for name, value in self.attributes:
            if name == key:
                return value
        return ""


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
    # Public semantic attributes projected from geography; coordinates and
    # sampling codes remain owned by the geography package.
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class WorldPlaceRelation:
    """One reviewed spatial relation between two registered public places."""

    subject_id: str
    relation: str
    object_id: str
    source_ref: str = ""


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
    geography_network: GeographyNetwork = field(default_factory=GeographyNetwork)
    place_relations: tuple[WorldPlaceRelation, ...] = ()
    access_rules: tuple[GeographyAccessRule, ...] = ()
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
    "GeographyNetwork",
    "GeographyAccessRule",
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
    "WorldPlaceRelation",
    "WorldStoryEvent",
    "VisitOpportunityRule",
)
