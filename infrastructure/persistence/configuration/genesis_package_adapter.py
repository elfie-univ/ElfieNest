"""Decode the version-bound ``config/genesis`` package for Genesis."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, cast

from elfie.genesis.contracts import KnowledgeLevel, MemoryCertainty
from elfie.genesis.world import (
    CoverageManifest,
    EarthArrivalRules,
    EpisodeTheme,
    GenerationPolicy,
    GenesisRoute,
    GenesisSourcePackage,
    KnowledgeCondition,
    LifeArchetypeRule,
    NameRules,
    RelationshipArchetype,
    SourcePackageManifest,
    SpatialPopulationCell,
    SpatialPopulationModel,
    WorldKnowledgeFact,
    WorldPlace,
    WorldStoryEvent,
)

from .config_store import read_yaml_mapping

_SPECIES_IDS = {"Saevi": "fox", "Tovren": "dog", "Myelle": "cat"}
_PLACE_KIND_ALIASES = {
    "public_space": "settlement_shared_space",
    "controlled_facility": "departure_facility",
}


def decode_genesis_package(
    program: Mapping[str, Any], program_path: Path
) -> GenesisSourcePackage:
    """Project the already integrity-checked package into existing domain types."""
    package_root = program_path.parent
    knowledge_doc = _member(package_root, "knowledge/elfaria.yaml")
    geography = _member(package_root, "knowledge/geography.yaml")
    rules = _mapping(program["rules"], "rules")
    world = _mapping(rules["world"], "rules.world")
    knowledge = tuple(_knowledge(item) for item in _array(knowledge_doc, "knowledge"))
    region_aliases = _geographic_place_regions(geography)
    places = tuple(
        _place(item, region_aliases.get(_text(_mapping(item, "world place"), "id"), ()))
        for item in _array(world, "places")
    ) + _region_places(geography)
    events = tuple(
        _event(item)
        for item in _array(_mapping(rules["events"], "rules.events"), "templates")
    )
    arrival = _mapping(rules["arrival"], "rules.arrival")
    after_arrival = _strings(arrival, "knowledge_after_arrival", default=())
    policy = _mapping(rules["policy"], "rules.policy")
    policy_episodes = _mapping(policy["episodes"], "rules.policy.episodes")
    policy_knowledge = _mapping(policy["knowledge"], "rules.policy.knowledge")
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
        knowledge=knowledge,
        unknown_boundaries=(),
        manifest=manifest,
        routes=_routes(world),
        spatial_population=_population(geography),
        name_rules=_name_rules(rules),
        generation_policy=GenerationPolicy(
            policy_version=_text(reproducibility, "domain_policy_version"),
            seed_algorithm=_text(reproducibility, "algorithm"),
            normal_episode_minimum=_integer(policy_episodes, "normal_minimum"),
            medium_knowledge_probability=medium_probability,
        ),
        earth_arrival_rules=EarthArrivalRules(
            eligible_life_stages=("youth", "young_adult", "mature", "elder"),
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
        episode_themes=_episode_themes(rules),
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
        topic=fact_id.split("-", maxsplit=1)[0],
        aliases=(),
        retrieval_terms=(fact_id,),
        level=level,
        certainty=cast(MemoryCertainty, "medium" if difficulty else "high"),
        status="active",
        source_ref=f"knowledge/elfaria.yaml#{fact_id}",
        related_ids=(),
        eligibility=tuple(condition.kind for condition in conditions),
        mastery_difficulty=difficulty,
        conditions=conditions,
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


def _place(raw: Any, region_aliases: tuple[str, ...] = ()) -> WorldPlace:
    item = _mapping(raw, "world place")
    place_id = _text(item, "id")
    kind = _PLACE_KIND_ALIASES.get(_text(item, "kind"), _text(item, "kind"))
    if place_id == "learning_healing_hall":
        kind = "learning_place"
    return WorldPlace(
        place_id=place_id,
        version=1,
        label=_text(item, "name"),
        kind=kind,
        parent_id=_text(item, "parent", required=False) or "elfaria",
        aliases=region_aliases,
        description=_text(item, "name"),
        status="active",
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


def _routes(world: Mapping[str, Any]) -> tuple[GenesisRoute, ...]:
    result = []
    for raw in _array(world, "routes"):
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
        WorldPlace(
            place_id=str(region_id),
            version=1,
            label=_text(_mapping(raw, f"regions.{region_id}"), "name"),
            kind="geographic_region",
            parent_id="mistyville",
            aliases=(),
            description=_text(_mapping(raw, f"regions.{region_id}"), "name"),
            status="active",
        )
        for region_id, raw in sorted(regions.items())
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
                life_stages=("youth", "young_adult", "mature", "elder"),
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


def _episode_themes(rules: Mapping[str, Any]) -> tuple[EpisodeTheme, ...]:
    group = _mapping(rules["episode_themes"], "rules.episode_themes")
    result = []
    for raw in _array(group, "themes"):
        item = _mapping(raw, "episode theme")
        result.append(
            EpisodeTheme(
                theme_id=_text(item, "id"),
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
