"""Load the single published Genesis source package.

This adapter owns YAML decoding and structural/package-integrity checks only.
All life-semantic decisions are made by :mod:`elfie.genesis` after the typed
package crosses this boundary.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from elfie.genesis.contracts import KnowledgeLevel, MemoryCertainty
from elfie.genesis.world import (
    CoverageLink,
    CoverageManifest,
    EarthArrivalRules,
    EpisodeTheme,
    GenerationPolicy,
    GenesisRoute,
    GenesisSourcePackage,
    LifeArchetypeRule,
    NameRules,
    RelationshipArchetype,
    SourcePackageManifest,
    SpatialPopulationCell,
    SpatialPopulationModel,
    WorldItemStatus,
    WorldKnowledgeFact,
    WorldPlace,
    WorldStoryEvent,
)

from .config_store import ConfigStoreError
from .documents import (
    BundledConfigSource,
    ConfigDocumentError,
    ConfigDocumentId,
    resolve_bundled_config_root,
)


class GenesisSourcePackageError(ConfigDocumentError):
    """The bundled creation source cannot cross the Genesis boundary."""


class BundledGenesisSource:
    """Decode and validate the one published Genesis source package."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = resolve_bundled_config_root(root)

    def load(self) -> GenesisSourcePackage:
        try:
            loaded = BundledConfigSource(self.root).load(
                ConfigDocumentId.GENESIS_SOURCE_PACKAGE
            )
        except (ConfigDocumentError, ConfigStoreError) as error:
            raise GenesisSourcePackageError(str(error)) from error
        try:
            package = _package(loaded.document)
            _validate_package(package, loaded.document)
            return package
        except (TypeError, ValueError, KeyError) as error:
            raise GenesisSourcePackageError(f"Genesis 资料包无效: {error}") from error


def load_genesis_source_package(*, root: Path | None = None) -> GenesisSourcePackage:
    """Load the published package through the registered config boundary."""

    return BundledGenesisSource(root).load()


def _package(document: Mapping[str, Any]) -> GenesisSourcePackage:
    region = _mapping(document["known_region"])
    relation = _mapping(document["earth_relation"])
    package_meta = _mapping(document.get("genesis", {}))
    manifest = SourcePackageManifest(
        package_id=_optional_text(
            package_meta, "package_id", f"{_text(document, 'world_id')}.genesis"
        ),
        package_version=_optional_text(
            package_meta, "package_version", _text(document, "package_version")
        ),
        schema_version=_optional_int(package_meta, "schema_version", 1),
        status=cast(
            Any,
            _optional_text(package_meta, "status", "published"),
        ),
        member_ids=_texts(package_meta, "member_ids", default=()),
        source_refs=_texts(package_meta, "source_refs", default=()),
        content_sha256=_optional_text(package_meta, "content_sha256", ""),
    )
    return GenesisSourcePackage(
        version=_int(document, "version"),
        schema_version=_int(document, "schema_version"),
        world_id=_text(document, "world_id"),
        display_name=_text(document, "display_name"),
        known_region_id=_text(region, "id"),
        known_region_name=_text(region, "name"),
        known_region_aliases=_texts(region, "aliases"),
        civilization_relation_to_earth=_text(
            relation, "civilization_relation_to_earth"
        ),
        earth_arrival_statement=_text(relation, "earth_arrival_statement"),
        earth_home_name=_text(relation, "earth_home_name"),
        earth_home_role=_text(relation, "earth_home_role"),
        places=tuple(_place(item) for item in _list(document, "places")),
        story_events=tuple(
            _story_event(item) for item in _list(document, "story_events")
        ),
        knowledge=tuple(_knowledge(item) for item in _list(document, "knowledge")),
        unknown_boundaries=_texts(document, "unknown_boundaries"),
        manifest=manifest,
        routes=_routes(package_meta),
        spatial_population=_population(package_meta),
        name_rules=_name_rules(package_meta),
        generation_policy=_generation_policy(package_meta),
        earth_arrival_rules=_arrival_rules(package_meta),
        coverage_manifest=_coverage_manifest(package_meta),
        life_archetypes=_life_archetypes(package_meta),
        relationship_archetypes=_relationship_archetypes(package_meta),
        episode_themes=_episode_themes(package_meta),
    )


def _place(raw: Any) -> WorldPlace:
    value = _mapping(raw)
    return WorldPlace(
        place_id=_text(value, "id"),
        version=_int(value, "version"),
        label=_text(value, "label"),
        kind=_text(value, "kind"),
        parent_id=_text(value, "parent_id"),
        aliases=_texts(value, "aliases"),
        description=_text(value, "description"),
        status=_status(value, "status"),
    )


def _story_event(raw: Any) -> WorldStoryEvent:
    value = _mapping(raw)
    return WorldStoryEvent(
        event_id=_text(value, "id"),
        version=_int(value, "version"),
        label=_text(value, "label"),
        summary=_text(value, "summary"),
        temporal_label=_text(value, "temporal_label"),
        aliases=_texts(value, "aliases"),
        source_ref=_text(value, "source_ref"),
    )


def _knowledge(raw: Any) -> WorldKnowledgeFact:
    value = _mapping(raw)
    variants = _variant_pairs(value.get("statement_variants", {}))
    return WorldKnowledgeFact(
        fact_id=_text(value, "id"),
        version=_int(value, "version"),
        statement=_text(value, "statement"),
        scope=_text(value, "scope"),
        topic=_text(value, "topic"),
        aliases=_texts(value, "aliases"),
        retrieval_terms=_texts(value, "retrieval_terms"),
        level=cast(KnowledgeLevel, _text(value, "level")),
        certainty=cast(MemoryCertainty, _text(value, "certainty")),
        status=_status(value, "status"),
        source_ref=_text(value, "source_ref"),
        related_ids=_texts(value, "related_ids"),
        eligibility=_texts(value, "eligibility"),
        importance=_optional_float(value, "importance", default=0.5),
        statement_variants=variants,
        epistemic_kind=cast(Any, _optional_text(value, "epistemic_kind", "documented")),
        prerequisite_ids=_texts(value, "prerequisite_ids", default=()),
        acquisition_channels=_texts(value, "acquisition_channels", default=()),
        exposure_weight=_optional_float(value, "exposure_weight", default=0.5),
    )


def _routes(value: Mapping[str, Any]) -> tuple[GenesisRoute, ...]:
    raw_routes = value.get("routes")
    if raw_routes is None:
        return ()
    if not isinstance(raw_routes, list):
        raise TypeError("genesis.routes 必须是数组")
    result = []
    for raw in raw_routes:
        item = _mapping(raw)
        result.append(
            GenesisRoute(
                route_id=_text(item, "id"),
                from_place_id=_text(item, "from_place_id"),
                to_place_id=_text(item, "to_place_id"),
                label=_text(item, "label"),
                aliases=_texts(item, "aliases", default=()),
                travel_time_band=_optional_text(
                    item, "travel_time_band", "通常需要一段时间"
                ),
                access_conditions=_texts(item, "access_conditions", default=()),
            )
        )
    return tuple(result)


def _population(value: Mapping[str, Any]) -> SpatialPopulationModel:
    raw_population = _mapping(value.get("population", {}))
    raw_cells = raw_population.get("cells")
    if raw_cells is None:
        raw_cells = []
    if not isinstance(raw_cells, list):
        raise TypeError("genesis.population.cells 必须是数组")
    cells = []
    for raw in raw_cells:
        item = _mapping(raw)
        species_ids = _texts(item, "species_ids")
        cells.append(
            SpatialPopulationCell(
                cell_id=_text(item, "id"),
                place_id=_text(item, "place_id"),
                species_ids=species_ids,
                weight=_number(item, "weight"),
                private_home_kind=_optional_text(
                    item, "private_home_kind", "household"
                ),
            )
        )
    weights = []
    raw_weights = raw_population.get("settlement_weights", {})
    if not isinstance(raw_weights, Mapping):
        raise TypeError("genesis.population.settlement_weights 必须是对象")
    for key, raw_weight in raw_weights.items():
        if not isinstance(key, str):
            raise TypeError("settlement weight ID 必须是字符串")
        weights.append((key, _number_value(raw_weight, f"settlement_weights.{key}")))
    return SpatialPopulationModel(tuple(cells), tuple(weights))


def _name_rules(value: Mapping[str, Any]) -> NameRules:
    raw_names = _mapping(value.get("names", {}))
    default = _texts(raw_names, "default", default=())
    raw_by_species = raw_names.get("by_species", {})
    if not isinstance(raw_by_species, Mapping):
        raise TypeError("genesis.names.by_species 必须是对象")
    by_species = tuple(
        (str(key), _texts(_mapping({"values": raw_values}), "values"))
        for key, raw_values in raw_by_species.items()
    )
    return NameRules(default_names=default, species_names=by_species)


def _generation_policy(value: Mapping[str, Any]) -> GenerationPolicy:
    raw_policy = _mapping(value.get("policy", {}))
    return GenerationPolicy(
        policy_version=_optional_text(raw_policy, "version", "generation-policy.v1"),
        seed_algorithm=_optional_text(
            raw_policy, "seed_algorithm", "blake2b-labeled-v1"
        ),
        relationship_count=_int_pair(raw_policy, "relationship_count", (10, 20)),
        episode_count=_int_pair(raw_policy, "episode_count", (3, 5)),
        salient_relationship_count=_int_pair(
            raw_policy, "salient_relationship_count", (3, 5)
        ),
        repeated_relationship_count=_int_pair(
            raw_policy, "repeated_relationship_count", (1, 2)
        ),
    )


def _arrival_rules(value: Mapping[str, Any]) -> EarthArrivalRules:
    raw = _mapping(value.get("arrival", {}))
    return EarthArrivalRules(
        eligible_species_ids=_texts(raw, "eligible_species_ids", default=()),
        eligible_life_stages=_texts(
            raw,
            "eligible_life_stages",
            default=("youth", "young_adult", "mature", "elder"),
        ),
        required_knowledge_ids=_texts(raw, "required_knowledge_ids", default=()),
        required_module_ids=_texts(raw, "required_module_ids", default=()),
    )


def _coverage_manifest(value: Mapping[str, Any]) -> CoverageManifest:
    raw = _mapping(value.get("coverage_manifest", {}))
    links_raw = raw.get("links", [])
    if not isinstance(links_raw, list):
        raise TypeError("genesis.coverage_manifest.links 必须是数组")
    links = []
    for item in links_raw:
        link = _mapping(item)
        disposition = _optional_text(link, "disposition", "mapped")
        if disposition not in ("mapped", "deferred", "excluded"):
            raise ValueError("coverage link disposition 无效")
        links.append(
            CoverageLink(
                upstream_id=_text(link, "upstream_id"),
                resident_fact_ids=_texts(link, "resident_fact_ids", default=()),
                disposition=cast(Any, disposition),
                rationale=_optional_text(link, "rationale", ""),
            )
        )
    return CoverageManifest(
        creator_source_ref=_optional_text(raw, "creator_source_ref", ""),
        resident_source_ref=_optional_text(raw, "resident_source_ref", ""),
        links=tuple(links),
    )


def _life_archetypes(value: Mapping[str, Any]) -> tuple[LifeArchetypeRule, ...]:
    raw_rules = value.get("life_archetypes", [])
    if not isinstance(raw_rules, list):
        raise TypeError("genesis.life_archetypes 必须是数组")
    result = []
    for raw in raw_rules:
        item = _mapping(raw)
        result.append(
            LifeArchetypeRule(
                archetype_id=_text(item, "id"),
                species_ids=_texts(item, "species_ids"),
                life_stages=_texts(item, "life_stages"),
                place_ids=_texts(item, "place_ids", default=()),
                weight=_number(item, "weight"),
                household_roles=_texts(item, "household_roles"),
                care_and_trade_context=_text(item, "care_and_trade_context"),
                learning_path_id=_text(item, "learning_path_id"),
                institution_ids=_texts(item, "institution_ids", default=()),
                apprenticeship_ids=_texts(item, "apprenticeship_ids", default=()),
                vocation_id=_text(item, "vocation_id"),
                proficiency_band=_text(item, "proficiency_band"),
                workplace_place_id=_optional_text(item, "workplace_place_id", ""),
            )
        )
    return tuple(result)


def _relationship_archetypes(
    value: Mapping[str, Any],
) -> tuple[RelationshipArchetype, ...]:
    raw_rules = value.get("relationship_archetypes", [])
    if not isinstance(raw_rules, list):
        raise TypeError("genesis.relationship_archetypes 必须是数组")
    result = []
    for raw in raw_rules:
        item = _mapping(raw)
        familiarity = _optional_text(item, "familiarity", "known")
        if familiarity not in ("intimate", "known", "acquainted", "heard"):
            raise ValueError("relationship archetype familiarity 无效")
        result.append(
            RelationshipArchetype(
                archetype_id=_text(item, "id"),
                role=_text(item, "role"),
                person_species_ids=_texts(item, "person_species_ids"),
                life_stages=_texts(item, "life_stages", default=()),
                weight=_number(item, "weight"),
                initial_trust=_optional_float(item, "initial_trust", default=0.5),
                importance=_optional_float(item, "importance", default=0.5),
                familiarity=cast(Any, familiarity),
                vocation_id=_optional_text(item, "vocation_id", ""),
                competency_ids=_texts(item, "competency_ids", default=()),
                episode_theme_ids=_texts(item, "episode_theme_ids", default=()),
            )
        )
    return tuple(result)


def _episode_themes(value: Mapping[str, Any]) -> tuple[EpisodeTheme, ...]:
    raw_themes = value.get("episode_themes", [])
    if not isinstance(raw_themes, list):
        raise TypeError("genesis.episode_themes 必须是数组")
    result = []
    for raw in raw_themes:
        item = _mapping(raw)
        required = item.get("required", False)
        if not isinstance(required, bool):
            raise TypeError("episode theme required 必须是布尔值")
        result.append(
            EpisodeTheme(
                theme_id=_text(item, "id"),
                label=_text(item, "label"),
                weight=_number(item, "weight"),
                life_stages=_texts(item, "life_stages"),
                min_age_years=_optional_int(item, "min_age_years", 1),
                required_roles=_texts(item, "required_roles", default=()),
                place_kinds=_texts(item, "place_kinds", default=()),
                emotional_tone=_text(item, "emotional_tone"),
                goal=_text(item, "goal"),
                obstacle=_text(item, "obstacle"),
                outcome=_text(item, "outcome"),
                impact=_text(item, "impact"),
                required_knowledge_ids=_texts(
                    item, "required_knowledge_ids", default=()
                ),
                required=required,
                order=_optional_int(item, "order", 0),
            )
        )
    return tuple(result)


def _validate_package(
    package: GenesisSourcePackage, document: Mapping[str, Any]
) -> None:
    if package.version < 1 or package.schema_version < 1:
        raise ValueError("资料包版本必须为正整数")
    if not package.is_published:
        raise ValueError("只有 published Genesis 资料包可以用于创建")
    if package.manifest.package_version != _text(document, "package_version"):
        raise ValueError("资料包版本与源文档版本不一致")
    if package.manifest.schema_version != package.schema_version:
        raise ValueError("资料包 manifest schema_version 不一致")
    if package.manifest.content_sha256:
        expected = _document_hash(document)
        if package.manifest.content_sha256.lower() != expected:
            raise ValueError("资料包内容摘要不一致")

    place_ids = {place.place_id for place in package.places}
    if len(place_ids) != len(package.places):
        raise ValueError("place ID 必须唯一")
    allowed_parents = {package.world_id, package.known_region_id, *place_ids, "earth"}
    for place in package.places:
        if place.parent_id not in allowed_parents:
            raise ValueError(f"地点 {place.place_id} 的 parent_id 未定义")
        if place.parent_id == place.place_id:
            raise ValueError(f"地点 {place.place_id} 不能以自身为父节点")

    event_ids = {event.event_id for event in package.story_events}
    if len(event_ids) != len(package.story_events):
        raise ValueError("story event ID 必须唯一")
    fact_ids = {fact.fact_id for fact in package.knowledge}
    if len(fact_ids) != len(package.knowledge):
        raise ValueError("knowledge ID 必须唯一")
    known_ids = (
        place_ids
        | event_ids
        | fact_ids
        | {
            package.world_id,
            package.known_region_id,
        }
    )
    for fact in package.knowledge:
        if fact.status == "active" and fact.level == "unknown":
            raise ValueError(f"active fact {fact.fact_id} 不能是 unknown level")
        if any(item not in known_ids for item in fact.related_ids):
            raise ValueError(f"fact {fact.fact_id} 引用了未定义 related_id")
        if any(item not in fact_ids for item in fact.prerequisite_ids):
            raise ValueError(f"fact {fact.fact_id} 引用了未定义 prerequisite_id")
    for event in package.story_events:
        if not event.source_ref.strip():
            raise ValueError(f"story event {event.event_id} 缺少 source_ref")
    for route in package.routes:
        if route.from_place_id not in place_ids or route.to_place_id not in place_ids:
            raise ValueError(f"route {route.route_id} 引用了未定义地点")
    for cell in package.spatial_population.cells:
        if cell.place_id not in place_ids:
            raise ValueError(f"population cell {cell.cell_id} 引用了未定义地点")
        if cell.weight <= 0.0:
            raise ValueError(f"population cell {cell.cell_id} 的权重必须为正")
    for fact_id in package.earth_arrival_rules.required_knowledge_ids:
        if fact_id not in fact_ids:
            raise ValueError(f"赴地规则引用了未定义知识 {fact_id}")
    required_modules = package.earth_arrival_rules.required_module_ids
    if "earth_program" not in required_modules:
        raise ValueError("赴地规则必须包含 earth_program 必修培训")
    if len(required_modules) != len(set(required_modules)):
        raise ValueError("赴地必修培训模块 ID 必须唯一")
    _validate_policy(package.generation_policy)
    _validate_catalogs(package, place_ids, fact_ids)


def _validate_catalogs(
    package: GenesisSourcePackage,
    place_ids: set[str],
    fact_ids: set[str],
) -> None:
    """Validate the static compiler catalogs before Genesis can sample them."""

    coverage = package.coverage_manifest
    if not coverage.creator_source_ref or not coverage.resident_source_ref:
        raise ValueError("published Genesis 资料包必须声明 CoverageManifest 来源")
    if not coverage.links:
        raise ValueError("published Genesis 资料包必须声明 CoverageManifest")
    upstream_ids = [link.upstream_id for link in coverage.links]
    if len(upstream_ids) != len(set(upstream_ids)):
        raise ValueError("CoverageManifest upstream ID 必须唯一")
    resident_ids = [
        resident_id for link in coverage.links for resident_id in link.resident_fact_ids
    ]
    if len(resident_ids) != len(set(resident_ids)):
        raise ValueError("CoverageManifest resident fact ID 必须唯一")
    if set(resident_ids) != fact_ids:
        raise ValueError("CoverageManifest 未完整覆盖 resident knowledge")
    for link in coverage.links:
        if link.disposition == "mapped" and not link.resident_fact_ids:
            raise ValueError(f"CoverageManifest {link.upstream_id} 缺少映射知识")
        if link.disposition != "mapped" and not link.rationale.strip():
            raise ValueError(
                f"CoverageManifest {link.upstream_id} 缺少 deferred/excluded 理由"
            )

    if not package.life_archetypes:
        raise ValueError("published Genesis 资料包必须包含 LifeArchetypeRules")
    life_ids = [rule.archetype_id for rule in package.life_archetypes]
    if len(life_ids) != len(set(life_ids)):
        raise ValueError("LifeArchetypeRules ID 必须唯一")
    for rule in package.life_archetypes:
        for place_id in (*rule.place_ids, rule.workplace_place_id):
            if place_id and place_id not in place_ids:
                raise ValueError(
                    f"LifeArchetypeRule {rule.archetype_id} 引用了未定义地点"
                )
        if not rule.species_ids or not rule.life_stages or not rule.vocation_id:
            raise ValueError(f"LifeArchetypeRule {rule.archetype_id} 条件不完整")

    if not package.relationship_archetypes:
        raise ValueError("published Genesis 资料包必须包含 RelationshipArchetypes")
    relationship_ids = [rule.archetype_id for rule in package.relationship_archetypes]
    if len(relationship_ids) != len(set(relationship_ids)):
        raise ValueError("RelationshipArchetypes ID 必须唯一")
    theme_ids = {theme.theme_id for theme in package.episode_themes}
    for rule in package.relationship_archetypes:
        if not rule.person_species_ids or not rule.role:
            raise ValueError(f"RelationshipArchetype {rule.archetype_id} 条件不完整")
        if set(rule.episode_theme_ids) - theme_ids:
            raise ValueError(
                f"RelationshipArchetype {rule.archetype_id} 引用了未定义经历主题"
            )

    if not package.episode_themes:
        raise ValueError("published Genesis 资料包必须包含 EpisodeThemeCatalog")
    if len(theme_ids) != len(package.episode_themes):
        raise ValueError("EpisodeThemeCatalog ID 必须唯一")
    for theme in package.episode_themes:
        if theme.min_age_years < 1 or not theme.life_stages:
            raise ValueError(f"EpisodeTheme {theme.theme_id} 年龄或生命阶段条件无效")
        if set(theme.required_knowledge_ids) - fact_ids:
            raise ValueError(f"EpisodeTheme {theme.theme_id} 引用了未定义知识")


def _validate_policy(policy: GenerationPolicy) -> None:
    for name in (
        "relationship_count",
        "episode_count",
        "salient_relationship_count",
        "repeated_relationship_count",
    ):
        minimum, maximum = getattr(policy, name)
        if minimum < 0 or maximum < minimum:
            raise ValueError(f"{name} 范围无效")


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.loads(json.dumps(document, ensure_ascii=False, default=str))
    genesis = payload.get("genesis")
    if isinstance(genesis, dict):
        genesis.pop("content_sha256", None)
    # Importance and exposure are tuning knobs for the personal compiler.  They
    # must not make an otherwise identical frozen source package unreadable;
    # semantic statements, references and publication rules remain covered by
    # the package digest.
    knowledge = payload.get("knowledge")
    if isinstance(knowledge, list):
        for atom in knowledge:
            if isinstance(atom, dict):
                atom.pop("importance", None)
                atom.pop("exposure_weight", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("必须是对象")
    return value


def _list(document: Mapping[str, Any], key: str) -> list[Any]:
    value = document[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} 必须是数组")
    return value


def _text(document: Mapping[str, Any], key: str) -> str:
    value = document[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value.strip()


def _optional_text(document: Mapping[str, Any], key: str, default: str) -> str:
    value = document.get(key, default)
    if not isinstance(value, str) or (value and not value.strip()):
        raise ValueError(f"{key} 必须是字符串")
    return value.strip()


def _int(document: Mapping[str, Any], key: str) -> int:
    value = document[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} 必须是整数")
    return value


def _optional_int(document: Mapping[str, Any], key: str, default: int) -> int:
    value = document.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} 必须是整数")
    return value


def _number(document: Mapping[str, Any], key: str) -> float:
    return _number_value(document[key], key)


def _number_value(value: Any, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 必须是数字")
    result = float(value)
    if result <= 0.0:
        raise ValueError(f"{key} 必须为正数")
    return result


def _optional_float(document: Mapping[str, Any], key: str, *, default: float) -> float:
    value = document.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 必须是数字")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{key} 必须在 [0, 1] 内")
    return result


def _texts(
    document: Mapping[str, Any], key: str, *, default: tuple[str, ...] | None = None
) -> tuple[str, ...]:
    if key not in document and default is not None:
        return default
    value = document[key]
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{key} 必须是字符串数组")
    return tuple(str(item).strip() for item in value)


def _variant_pairs(value: Any) -> tuple[tuple[str, str], ...]:
    if value in ({}, None):
        return ()
    if not isinstance(value, Mapping):
        raise TypeError("statement_variants 必须是对象")
    result = []
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str) or not item.strip():
            raise ValueError("statement_variants 必须是非空字符串映射")
        result.append((key, item.strip()))
    return tuple(result)


def _int_pair(
    document: Mapping[str, Any], key: str, default: tuple[int, int]
) -> tuple[int, int]:
    value = document.get(key, default)
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        raise ValueError(f"{key} 必须是两个整数")
    return int(value[0]), int(value[1])


def _status(document: Mapping[str, Any], key: str) -> WorldItemStatus:
    value = _text(document, key)
    if value not in ("active", "unknown-boundary"):
        raise ValueError(f"{key} 状态无效")
    return cast(WorldItemStatus, value)


__all__ = (
    "BundledGenesisSource",
    "GenesisSourcePackageError",
    "load_genesis_source_package",
)
