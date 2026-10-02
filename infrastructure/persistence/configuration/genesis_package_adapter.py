"""Decode the version-bound ``config/genesis`` package for Genesis."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, cast

from elfie.brain.memory.memory_records import AssertionInput, NodeInput
from elfie.brain.memory.ontology import MemoryOntologySnapshot
from elfie.genesis.contracts import KnowledgeLevel
from elfie.genesis.world import (
    CoverageManifest,
    EarthArrivalRules,
    EpisodeTheme,
    GenerationPolicy,
    GenesisRoute,
    GenesisSourcePackage,
    GeographyAccessRule,
    GeographyNetwork,
    KnowledgeCondition,
    LifeArchetypeRule,
    NameRules,
    RelationshipArchetype,
    SourcePackageManifest,
    SpatialPopulationCell,
    SpatialPopulationModel,
    VisitOpportunityRule,
    WorldKnowledgeFact,
    WorldPlace,
    WorldPlaceRelation,
    WorldStoryEvent,
)

from .config_store import read_yaml_mapping
from .family import load_family_generation_config
from .public_events import load_learning_policy, load_public_event_catalog

_SPECIES_IDS = {"Saevi": "saevi", "Tovren": "tovren", "Myelle": "myelle"}
_PLACE_KIND_ALIASES = {
    "public_space": "settlement_shared_space",
    "controlled_facility": "departure_facility",
}


def decode_genesis_package(
    program: Mapping[str, Any],
    program_path: Path,
    *,
    ontology: MemoryOntologySnapshot,
) -> GenesisSourcePackage:
    """Project the already integrity-checked package into existing domain types."""
    package_root = program_path.parent
    family_document = _member(package_root, "family.yaml")
    knowledge_doc = _member(package_root, "knowledge/elfaria.yaml")
    geography = _member(package_root, "knowledge/geography.yaml")
    rules = _mapping(program["rules"], "rules")
    world = _mapping(rules["world"], "rules.world")
    world_calendar = _mapping(world["calendar"], "rules.world.calendar")
    knowledge = tuple(_knowledge(item) for item in _array(knowledge_doc, "knowledge"))
    region_aliases = _geographic_place_regions(geography)
    if _text(world, "place_registry_ref") != "knowledge/geography.yaml#places":
        raise ValueError("地点注册表必须由 geography.yaml 提供")
    if _text(world, "route_aliases_ref") != "knowledge/geography.yaml#route_aliases":
        raise ValueError("路线别名必须由 geography.yaml 提供")
    places = tuple(
        _geography_place(
            item,
            region_aliases.get(_text(_mapping(item, "geographic place"), "id"), ()),
        )
        for item in _array(geography, "places")
    ) + _region_places(geography)
    place_relations = _place_relations(geography)
    public_events = load_public_event_catalog(
        _member(package_root, "events.yaml"),
        place_ids=tuple(place.place_id for place in places),
    )
    if public_events.days_per_year != _integer(world_calendar, "days_per_local_year"):
        raise ValueError("Public event calendar differs from world calendar")
    access_rules = _access_rules(world)
    events = tuple(
        _event(item)
        for item in _array(_mapping(rules["events"], "rules.events"), "templates")
    )
    arrival = _mapping(rules["arrival"], "rules.arrival")
    after_arrival = _strings(arrival, "knowledge_after_arrival", default=())
    policy = _mapping(rules["policy"], "rules.policy")
    policy_episodes = _mapping(policy["episodes"], "rules.policy.episodes")
    candidate_rules = _mapping(policy["candidates"], "rules.policy.candidates")
    backtracking = _mapping(policy["backtracking"], "rules.policy.backtracking")
    age_policy = _mapping(
        candidate_rules["age_policy"], "rules.policy.candidates.age_policy"
    )
    stage_weights = _mapping(
        age_policy["stage_weights"],
        "rules.policy.candidates.age_policy.stage_weights",
    )
    policy_knowledge = _mapping(policy["knowledge"], "rules.policy.knowledge")
    family_config = load_family_generation_config(family_document)
    importance_policy = _mapping(policy["importance"], "rules.policy.importance")
    importance_baselines = _mapping(
        importance_policy["role_baselines"], "rules.policy.importance.role_baselines"
    )
    visits_policy = _mapping(policy["visits"], "rules.policy.visits")
    personality_multipliers = _mapping(
        visits_policy["personality_multipliers"],
        "rules.policy.visits.personality_multipliers",
    )
    social_multiplier = _mapping(
        personality_multipliers["social"],
        "rules.policy.visits.personality_multipliers.social",
    )
    curiosity_multiplier = _mapping(
        personality_multipliers["curiosity"],
        "rules.policy.visits.personality_multipliers.curiosity",
    )
    risk_multiplier = _mapping(
        personality_multipliers["risk"],
        "rules.policy.visits.personality_multipliers.risk",
    )
    visit_opportunities = _visit_opportunities(policy)
    reproducibility = _mapping(
        policy["reproducibility"], "rules.policy.reproducibility"
    )
    probabilities = _mapping(
        policy_knowledge["mastery_probabilities"], "mastery_probabilities"
    )
    medium_probability = _probability(_mapping(probabilities["medium"], "medium"))
    source_entries = _mapping(program["sources"], "sources")
    world_source = _mapping(source_entries["world"], "sources.world")
    resident_source = _mapping(source_entries["resident"], "sources.resident")
    manifest_doc = _mapping(program["manifest"], "manifest")
    family_members = tuple(
        _mapping(item, "manifest member")
        for item in _array(manifest_doc, "members")
        if _text(_mapping(item, "manifest member"), "path") == "family.yaml"
    )
    if (
        len(family_members) != 1
        or _text(family_members[0], "version") != family_config.generation_version
    ):
        raise ValueError("family.yaml 与 Genesis manifest 的版本不一致")
    manifest = SourcePackageManifest(
        package_id=_text(manifest_doc, "package_id"),
        package_version=_text(manifest_doc, "package_version"),
        schema_version=1,
        status=cast(Any, _text(manifest_doc, "status")),
        member_ids=tuple(
            _text(_mapping(item, "member"), "path")
            for item in _array(manifest_doc, "members")
        ),
        source_refs=tuple(
            _text(value, "path") for value in (world_source, resident_source)
        ),
        content_sha256=_text(manifest_doc, "content_sha256"),
    )
    return GenesisSourcePackage(
        version=_integer(program, "version"),
        schema_version=_integer(program, "schema_version"),
        world_id="elfaria",
        display_name="Elfaria",
        known_region_id="mistyville",
        known_region_name="迷雾镇",
        known_region_aliases=("Mistyville",),
        civilization_relation_to_earth="有限且不稳定的联系",
        earth_arrival_statement=_statement(knowledge, "E-08"),
        earth_home_name="ElfieNest",
        earth_home_role="抵达后的生活基地和家",
        places=places,
        story_events=events,
        public_events=public_events,
        learning_policy=load_learning_policy(
            _mapping(rules["learning"], "rules.learning"),
            days_per_year=public_events.days_per_year,
        ),
        knowledge=knowledge,
        unknown_boundaries=(),
        manifest=manifest,
        routes=_routes(geography),
        geography_network=_geography_network(
            geography,
            days_per_local_year=_integer(world_calendar, "days_per_local_year"),
        ),
        place_relations=place_relations,
        access_rules=access_rules,
        spatial_population=_population(geography),
        name_rules=_name_rules(rules),
        generation_policy=GenerationPolicy(
            knowledge_episode_max_chars=_integer(policy_knowledge, "episode_max_chars"),
            policy_version=_text(reproducibility, "domain_policy_version"),
            seed_algorithm=_text(reproducibility, "algorithm"),
            normal_episode_minimum=_integer(policy_episodes, "normal_minimum"),
            medium_knowledge_probability=medium_probability,
            candidate_proposal_count=_integer(
                candidate_rules, "existing_engine_proposals_per_role"
            ),
            candidate_options_per_choice=_integer(backtracking, "options_per_choice"),
            candidate_total_backtracks=_integer(backtracking, "total_backtracks"),
            candidate_minimum_age_years=_integer(
                candidate_rules, "integer_age_minimum"
            ),
            candidate_age_reserve_years=_integer(age_policy, "terminal_reserve_years"),
            candidate_stage_weights=tuple(
                (
                    stage,
                    _bounded_probability(
                        stage_weights,
                        stage,
                        "rules.policy.candidates.age_policy.stage_weights",
                    ),
                )
                for stage in ("childhood", "adolescent", "mature", "elder")
            ),
            family=family_config,
            relationship_importance_baselines=tuple(
                (
                    str(role),
                    _bounded_probability(
                        importance_baselines,
                        str(role),
                        "rules.policy.importance.role_baselines",
                    ),
                )
                for role in sorted(importance_baselines)
            ),
            relationship_layer_decay_lambda=_number(
                importance_policy, "relationship_layer_decay_lambda"
            ),
            friend_layer_decay_lambda=_number(
                importance_policy, "friend_layer_decay_lambda"
            ),
            public_contact_count_distribution=_contact_distribution(
                rules, "public_contact_count_distribution"
            ),
            cohort_count_distribution=_contact_distribution(
                rules, "cohort_count_distribution"
            ),
            public_contact_reuse_probability=_number(
                _mapping(rules["social_graph"], "social_graph"),
                "public_contact_reuse_probability",
            ),
            friend_contact_beta=_number(importance_policy, "friend_contact_beta"),
            friend_max_count=_integer(importance_policy, "friend_max_count"),
            visit_sampler_version=_text(visits_policy, "sampler_version"),
            visit_repeat_count_power=_number(visits_policy, "repeat_count_power"),
            visit_social_multiplier_base=_number(social_multiplier, "base"),
            visit_social_multiplier_slope=_number(social_multiplier, "slope"),
            visit_curiosity_multiplier_base=_number(curiosity_multiplier, "base"),
            visit_curiosity_multiplier_slope=_number(curiosity_multiplier, "slope"),
            visit_risk_multiplier_base=_number(risk_multiplier, "base"),
            visit_risk_openness_slope=_number(risk_multiplier, "openness_slope"),
            visit_risk_neuroticism_slope=_number(risk_multiplier, "neuroticism_slope"),
            visit_cross_region_lifetime_fraction=_number(
                visits_policy, "cross_region_lifetime_fraction"
            ),
            visit_opportunities=visit_opportunities,
        ),
        earth_arrival_rules=EarthArrivalRules(
            earth_label=_text(arrival, "earth_label"),
            owner_home_label=_text(arrival, "owner_home_label"),
            eligible_life_stages=("childhood", "adolescent", "mature", "elder"),
            required_knowledge_ids=("E-08",),
            post_arrival_knowledge_ids=after_arrival,
            preparation_duration_local_days=_integer(arrival, "duration_local_days"),
        ),
        coverage_manifest=CoverageManifest(
            creator_source_ref=_text(world_source, "path"),
            resident_source_ref=_text(resident_source, "path"),
        ),
        life_archetypes=_life_archetypes(rules),
        relationship_archetypes=_relationship_archetypes(rules),
        episode_themes=_episode_themes(rules, ontology),
    )


def _member(root: Path, relative: str) -> Mapping[str, Any]:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError(f"不安全的 Genesis member 路径: {relative}")
    return read_yaml_mapping(root.joinpath(*path.parts))


def _knowledge(raw: Any) -> WorldKnowledgeFact:
    item = _mapping(raw, "knowledge unit")
    conditions = _conditions(item.get("eligibility"))
    fact_id = _text(item, "id")
    difficulty = _text(item, "mastery_difficulty", required=False)
    if difficulty not in ("", "medium"):
        raise ValueError(f"不支持的知识难度: {difficulty}")
    levels: tuple[KnowledgeLevel, ...] = ("common", "regional", "specialist", "unknown")
    level: KnowledgeLevel = (
        "specialist"
        if any(c.kind in ("route", "experience", "vocation") for c in conditions)
        else "regional"
        if conditions
        else "common"
    )
    if level not in levels:
        raise ValueError("knowledge level 无效")
    return WorldKnowledgeFact(
        fact_id=fact_id,
        version=1,
        statement=_text(item, "description"),
        scope="resident",
        topic=_text(item, "topic"),
        aliases=(),
        retrieval_terms=(fact_id,),
        level=level,
        certainty="medium" if difficulty else "high",
        status="active",
        source_ref=f"knowledge/elfaria.yaml#{fact_id}",
        related_ids=(),
        eligibility=tuple(condition.kind for condition in conditions),
        mastery_difficulty=difficulty,
        conditions=conditions,
        graph_nodes=tuple(
            NodeInput(
                node_id=_text(node, "id"),
                node_type=_text(node, "type"),
                canonical_label=_text(node, "label"),
                scope="elfie",
                properties={"entity_level": _text(node, "level")},
            )
            for node in item.get("graph_nodes", ())
        ),
        graph_assertions=tuple(
            AssertionInput(
                subject_id=_text(edge, "subject"),
                predicate=_text(edge, "predicate"),
                object_node_id=edge.get("object"),
                object_literal=edge.get("literal"),
                context=f"resident-knowledge:{fact_id}",
            )
            for edge in item.get("graph_assertions", ())
        ),
    )


def _conditions(raw: Any) -> tuple[KnowledgeCondition, ...]:
    if raw is None:
        return ()
    eligibility = _mapping(raw, "eligibility")
    if set(eligibility) != {"all"}:
        raise ValueError("knowledge eligibility 只接受明确的 all 条件")
    result: list[KnowledgeCondition] = []
    for raw_condition in _array(eligibility, "all"):
        condition = _mapping(raw_condition, "eligibility condition")
        if len(condition) != 1:
            raise ValueError("eligibility condition 必须恰有一个类型")
        kind, raw_attributes = next(iter(condition.items()))
        if kind not in ("place", "route", "experience", "vocation"):
            raise ValueError(f"未知 eligibility 类型: {kind}")
        attributes = _mapping(raw_attributes, f"{kind} condition")
        normalized = tuple(
            sorted((str(key), str(value)) for key, value in attributes.items())
        )
        if not normalized:
            raise ValueError(f"{kind} condition 不能为空")
        result.append(KnowledgeCondition(cast(Any, kind), normalized))
    return tuple(result)


def _geography_place(raw: Any, region_aliases: tuple[str, ...] = ()) -> WorldPlace:
    """Project the geography member's complete public place registry."""
    item = _mapping(raw, "geographic place")
    place_id = _text(item, "id")
    kind = _PLACE_KIND_ALIASES.get(_text(item, "kind"), _text(item, "kind"))
    if place_id == "learning_healing_hall":
        kind = "learning_place"
    elif place_id == "skyreach_square":
        kind = "settlement_shared_space"
    label = _text(item, "name")
    metadata = []
    access = _text(item, "access", required=False)
    if access:
        metadata.append(("access", access))
    range_semantics = _text(item, "range_semantics", required=False)
    if range_semantics:
        metadata.append(("range_semantics", range_semantics))
    return WorldPlace(
        place_id=place_id,
        version=1,
        label=label,
        kind=kind,
        parent_id=_text(item, "parent_id", required=False) or "elfaria",
        aliases=region_aliases,
        description=_text(item, "description", required=False) or label,
        status="active",
        metadata=tuple(metadata),
    )


def _event(raw: Any) -> WorldStoryEvent:
    item = _mapping(raw, "event template")
    event_id = _text(item, "id")
    return WorldStoryEvent(
        event_id=event_id,
        version=1,
        label=event_id,
        summary=event_id,
        temporal_label="",
        aliases=(),
        source_ref=f"program.yaml#rules.events.{event_id}",
    )


def _routes(geography: Mapping[str, Any]) -> tuple[GenesisRoute, ...]:
    result = []
    for raw in _array(geography, "route_aliases"):
        item = _mapping(raw, "route")
        result.append(
            GenesisRoute(
                route_id=_text(item, "id"),
                from_place_id=_text(item, "from"),
                to_place_id=_text(item, "to"),
                label=_text(item, "id"),
            )
        )
    return tuple(result)


def _geography_network(
    geography: Mapping[str, Any], *, days_per_local_year: int = 196
) -> GeographyNetwork:
    """Project the reviewed grid/path rules for Genesis feasibility checks."""

    grid = _mapping(geography["grid"], "grid")
    raw_matrix = _array(grid, "region_matrix")
    if any(not isinstance(row, list) for row in raw_matrix):
        raise TypeError("region_matrix 的每一行必须是数组")
    region_matrix = tuple(tuple(str(value) for value in row) for row in raw_matrix)
    network = _mapping(geography["network"], "network")
    raw_paths = _array(network, "land_backbone_paths")
    if any(not isinstance(path, list) for path in raw_paths):
        raise TypeError("land_backbone_paths 的每一条路径必须是数组")
    land_backbone_paths = tuple(
        tuple(str(value).strip() for value in path) for path in raw_paths
    )
    water = _mapping(network["water"], "network.water")
    water_edges = tuple(
        (
            _text(_mapping(edge, "water edge"), "from"),
            _text(_mapping(edge, "water edge"), "to"),
            _integer(_mapping(edge, "water edge"), "water_grid_hops"),
        )
        for edge in _array(water, "grid_hop_edges")
    )
    ferry_nodes = tuple(_strings(water, "ferry_nodes"))
    island_destinations = tuple(
        (
            _text(_mapping(destination, "island destination"), "place_id"),
            _text(_mapping(destination, "island destination"), "cell"),
            _text(_mapping(destination, "island destination"), "from_ferry"),
            _integer(_mapping(destination, "island destination"), "water_grid_hops"),
        )
        for destination in _array(water, "island_destinations")
    )
    place_cells: list[tuple[str, str]] = []
    for raw_place in _array(geography, "places"):
        place = _mapping(raw_place, "geographic place")
        cell = _text(place, "cell", required=False)
        if cell:
            place_cells.append((_text(place, "id"), cell))
    travel_policy = _mapping(geography["travel_policy"], "travel_policy")
    return GeographyNetwork(
        region_matrix=region_matrix,
        land_backbone_paths=land_backbone_paths,
        water_grid_hop_edges=water_edges,
        island_destinations=island_destinations,
        ferry_nodes=ferry_nodes,
        place_cells=tuple(sorted(place_cells)),
        land_days_per_grid_hop=_integer(travel_policy, "land_days_per_grid_hop"),
        water_days_per_grid_hop=_integer(travel_policy, "water_days_per_grid_hop"),
        days_per_local_year=days_per_local_year,
    )


def _place_relations(
    geography: Mapping[str, Any],
) -> tuple[WorldPlaceRelation, ...]:
    result: list[WorldPlaceRelation] = []
    for raw in _array(geography, "place_relations"):
        item = _mapping(raw, "place relation")
        subject_id = _text(item, "subject")
        relation = _text(item, "relation")
        object_id = _text(item, "object")
        result.append(
            WorldPlaceRelation(
                subject_id=subject_id,
                relation=relation,
                object_id=object_id,
                source_ref=f"knowledge/geography.yaml#place_relations:{subject_id}:{relation}:{object_id}",
            )
        )
    return tuple(result)


def _access_rules(world: Mapping[str, Any]) -> tuple[GeographyAccessRule, ...]:
    result: list[GeographyAccessRule] = []
    for raw in _array(world, "access_rules"):
        item = _mapping(raw, "geography access rule")
        result.append(
            GeographyAccessRule(
                rule_id=_text(item, "id"),
                place_id=_text(item, "place_ref"),
                requires=_strings(item, "requires", default=()),
                ordinary_travel_allowed=bool(item.get("ordinary_travel_allowed", True)),
                observation_only=bool(item.get("observation_only", False)),
                landing_is_island=bool(item.get("landing_is_island", False)),
            )
        )
    return tuple(result)


def _population(geography: Mapping[str, Any]) -> SpatialPopulationModel:
    grid = _mapping(geography["grid"], "grid")
    regions = _mapping(geography["regions"], "regions")
    matrix = _array(grid, "region_matrix")
    cells: list[SpatialPopulationCell] = []
    for row, region_row in enumerate(matrix):
        for column, region_id in enumerate(region_row):
            region = _mapping(regions[str(region_id)], f"regions.{region_id}")
            if not region.get("birth_eligible", False):
                continue
            species = _strings(region, "allowed_species")
            if not species:
                continue
            cells.append(
                SpatialPopulationCell(
                    cell_id=f"u-r{row:02d}-c{column:02d}",
                    region_id=str(region_id),
                    place_id=str(region_id),
                    species_ids=tuple(_SPECIES_IDS[name] for name in species),
                    weight=1.0,
                )
            )
    return SpatialPopulationModel(tuple(cells))


def _region_places(geography: Mapping[str, Any]) -> tuple[WorldPlace, ...]:
    regions = _mapping(geography["regions"], "regions")
    return tuple(
        _region_place(region_id, _mapping(raw, f"regions.{region_id}"))
        for region_id, raw in sorted(regions.items())
    )


def _region_place(region_id: str, raw: Mapping[str, Any]) -> WorldPlace:
    label = _text(raw, "name")
    terrain = _text(raw, "terrain", required=False)
    macro_region = _text(raw, "macro_region", required=False)
    allowed_species = _strings(raw, "allowed_species", default=())
    habitable = bool(raw.get("habitable", False))
    birth_eligible = bool(raw.get("birth_eligible", False))
    description_parts = [label]
    if terrain:
        description_parts.append(f"地貌：{terrain}")
    if allowed_species:
        description_parts.append(f"居住物种：{'、'.join(allowed_species)}")
    description_parts.append("可出生" if birth_eligible else "不可作为出生地")
    metadata = tuple(
        sorted(
            (
                ("terrain", terrain),
                ("macro_region", macro_region),
                ("resident_species", "、".join(allowed_species)),
                ("habitable", "true" if habitable else "false"),
                ("birth_eligible", "true" if birth_eligible else "false"),
            )
        )
    )
    return WorldPlace(
        place_id=str(region_id),
        version=1,
        label=label,
        kind="geographic_region",
        parent_id=_text(raw, "parent_place_id"),
        aliases=(),
        description="；".join(description_parts),
        status="active",
        metadata=metadata,
    )


def _geographic_place_regions(
    geography: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for raw in _array(geography, "places"):
        item = _mapping(raw, "geographic place")
        place_id = _text(item, "id")
        regions = _strings(item, "regions", default=())
        if regions:
            result[place_id] = regions
    return result


def _name_rules(rules: Mapping[str, Any]) -> NameRules:
    raw = _mapping(rules["names"], "rules.names")
    lexicon = _mapping(raw["private_name_lexicon"], "private_name_lexicon")
    specific = _mapping(lexicon["species_preference"], "species_preference")
    return NameRules(
        default_names=_strings(lexicon, "default"),
        species_names=tuple(
            (_SPECIES_IDS[name], _strings(specific, name)) for name in _SPECIES_IDS
        ),
    )


def _life_archetypes(rules: Mapping[str, Any]) -> tuple[LifeArchetypeRule, ...]:
    group = _mapping(rules["life_archetypes"], "rules.life_archetypes")
    result = []
    for raw in _array(group, "archetypes"):
        item = _mapping(raw, "life archetype")
        species = _strings(item, "applicable_species")
        result.append(
            LifeArchetypeRule(
                archetype_id=_text(item, "id"),
                species_ids=tuple(_SPECIES_IDS[name] for name in species),
                life_stages=_strings(item, "applicable_stages"),
                place_ids=(),
                weight=_number(item, "weight"),
                household_roles=_strings(item, "household_roles"),
                care_and_trade_context=_text(item, "care_and_trade_context"),
                learning_path_id=_text(item, "learning_path_ref"),
                institution_ids=(),
                apprenticeship_ids=_strings(item, "apprenticeship_refs"),
                vocation_id="",
                proficiency_band="",
                workplace_place_id="",
            )
        )
    return tuple(result)


def _relationship_archetypes(
    rules: Mapping[str, Any],
) -> tuple[RelationshipArchetype, ...]:
    group = _mapping(rules["relationship_archetypes"], "rules.relationship_archetypes")
    result = []
    for raw in _array(group, "archetypes"):
        item = _mapping(raw, "relationship archetype")
        result.append(
            RelationshipArchetype(
                archetype_id=_text(item, "id"),
                role=_text(item, "role"),
                person_species_ids=tuple(
                    _SPECIES_IDS[name] for name in _strings(item, "species")
                ),
                life_stages=("childhood", "adolescent", "mature", "elder"),
                weight=_number(item, "weight"),
                initial_trust=_number(item, "initial_trust"),
                importance=_number(item, "importance"),
                familiarity=cast(Any, _text(item, "familiarity")),
                vocation_id="",
                competency_ids=_strings(item, "competency_ids"),
                episode_theme_ids=_strings(item, "episode_theme_ids"),
            )
        )
    return tuple(result)


def _visit_opportunities(
    policy: Mapping[str, Any],
) -> tuple[VisitOpportunityRule, ...]:
    group = _mapping(policy["visits"], "rules.policy.visits")
    result: list[VisitOpportunityRule] = []
    for raw in _array(group, "opportunities"):
        item = _mapping(raw, "visit opportunity")
        member_probabilities = _mapping(
            item.get("member_probabilities", {}),
            "visit opportunity member probabilities",
        )
        purpose_weights = _mapping(
            item.get("purpose_weights", {}), "visit opportunity purpose weights"
        )
        species_multipliers = _mapping(
            item.get("species_multipliers", {}), "visit opportunity species multipliers"
        )
        region_multipliers = _mapping(
            item.get("region_multipliers", {}), "visit opportunity region multipliers"
        )
        regional_probabilities = _mapping(
            item.get("base_visit_probabilities_by_region", {}),
            "visit opportunity base probabilities by region",
        )
        personality_factors = _mapping(
            item.get("personality_factor_by_purpose", {}),
            "visit opportunity personality factors",
        )
        result.append(
            VisitOpportunityRule(
                opportunity_id=_text(item, "id"),
                place_ids=_strings(item, "place_ids"),
                base_visit_probability=_bounded_probability(
                    item,
                    "base_visit_probability",
                    "rules.policy.visits.opportunities",
                ),
                home_regions=_strings(item, "home_regions", default=()),
                base_visit_probabilities_by_region=tuple(
                    (
                        str(region_id),
                        _bounded_probability(
                            regional_probabilities,
                            str(region_id),
                            "visit opportunity base probabilities by region",
                        ),
                    )
                    for region_id in sorted(regional_probabilities)
                ),
                minimum_age_years=_integer(item, "minimum_age_years"),
                purpose=_text(item, "purpose"),
                stay_days=_integer(item, "stay_days"),
                max_repeat_count=_integer(item, "max_repeat_count"),
                member_probability=_bounded_probability(
                    item, "member_probability", "rules.policy.visits.opportunities"
                ),
                member_probabilities=tuple(
                    (
                        str(place_id),
                        _bounded_probability(
                            member_probabilities,
                            str(place_id),
                            "visit opportunity member probabilities",
                        ),
                    )
                    for place_id in sorted(member_probabilities)
                ),
                purpose_weights=tuple(
                    (str(purpose), _number(purpose_weights, str(purpose)))
                    for purpose in sorted(purpose_weights)
                ),
                personality_factor_by_purpose=tuple(
                    (str(purpose), str(factor))
                    for purpose, factor in sorted(personality_factors.items())
                ),
                species_multipliers=tuple(
                    (str(species_id), _number(species_multipliers, str(species_id)))
                    for species_id in sorted(species_multipliers)
                ),
                region_multipliers=tuple(
                    (str(region_id), _number(region_multipliers, str(region_id)))
                    for region_id in sorted(region_multipliers)
                ),
                requires_opportunity_id=_text(
                    item, "requires_opportunity_id", required=False
                ),
                distance_decay_days=_number(item, "distance_decay_days"),
            )
        )
    return tuple(result)


def _episode_themes(
    rules: Mapping[str, Any], ontology: MemoryOntologySnapshot
) -> tuple[EpisodeTheme, ...]:
    group = _mapping(rules["episode_themes"], "rules.episode_themes")
    result = []
    for raw in _array(group, "themes"):
        item = _mapping(raw, "episode theme")
        event_kind = _text(item, "event_kind")
        try:
            ontology.validate_episode_type(event_kind)
        except ValueError as error:
            raise ValueError(
                f"EpisodeTheme {item.get('id')} event_kind 无效: {event_kind}"
            ) from error
        result.append(
            EpisodeTheme(
                theme_id=_text(item, "id"),
                event_kind=cast(Any, event_kind),
                label=_text(item, "label"),
                weight=_number(item, "weight"),
                life_stages=_strings(item, "life_stages"),
                min_age_years=_integer(item, "minimum_age_local_years"),
                required_roles=_strings(item, "required_roles", default=()),
                place_kinds=_strings(item, "place_kinds", default=()),
                emotional_tone=_text(item, "emotional_tone"),
                goal=_text(item, "goal"),
                obstacle=_text(item, "obstacle"),
                outcome=_text(item, "outcome"),
                impact=_text(item, "impact"),
                required_knowledge_ids=_strings(
                    item, "required_knowledge_ids", default=()
                ),
                required=bool(item.get("required", False)),
                order=_integer(item, "order"),
            )
        )
    return tuple(result)


def _statement(facts: tuple[WorldKnowledgeFact, ...], fact_id: str) -> str:
    return next(fact.statement for fact in facts if fact.fact_id == fact_id)


def _probability(raw: Mapping[str, Any]) -> float:
    numerator = _integer(raw, "numerator")
    denominator = _integer(raw, "denominator")
    if denominator <= 0 or not 0 <= numerator <= denominator:
        raise ValueError("mastery probability 无效")
    return numerator / denominator


def _bounded_probability(value: Mapping[str, Any], key: str, label: str) -> float:
    result = _number(value, key)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{label}.{key} 必须在 [0, 1] 内")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} 必须是对象")
    return value


def _array(value: Mapping[str, Any], key: str) -> list[Any]:
    result = value[key]
    if not isinstance(result, list):
        raise TypeError(f"{key} 必须是数组")
    return result


def _text(value: Mapping[str, Any], key: str, *, required: bool = True) -> str:
    item = value.get(key, "")
    if not isinstance(item, str) or (required and not item.strip()):
        raise ValueError(f"{key} 必须是非空字符串")
    return item.strip()


def _integer(value: Mapping[str, Any], key: str) -> int:
    item = value[key]
    if isinstance(item, bool) or not isinstance(item, int):
        raise ValueError(f"{key} 必须是整数")
    return item


def _number(value: Mapping[str, Any], key: str) -> float:
    item = value[key]
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise ValueError(f"{key} 必须是数字")
    return float(item)


def _strings(
    value: Mapping[str, Any], key: str, *, default: tuple[str, ...] | None = None
) -> tuple[str, ...]:
    raw = value.get(key, default)
    if not isinstance(raw, (list, tuple)) or any(
        not isinstance(item, str) for item in raw
    ):
        raise ValueError(f"{key} 必须是字符串数组")
    return tuple(item.strip() for item in raw)


def _contact_distribution(
    rules: Mapping[str, Any], key: str
) -> tuple[tuple[int, float], ...]:
    values = _mapping(_mapping(rules["social_graph"], "social_graph")[key], key)
    result = tuple((int(count), float(weight)) for count, weight in values.items())
    if (
        not result
        or any(
            count < 0 or weight < 0 or not math.isfinite(weight)
            for count, weight in result
        )
        or abs(sum(w for _, w in result) - 1.0) > 1e-9
    ):
        raise ValueError(f"Invalid social graph distribution: {key}")
    return result
