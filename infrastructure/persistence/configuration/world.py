"""Loader for the immutable, bundled Elfaria World Canon."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from elfie.genesis.contracts import KnowledgeLevel, MemoryCertainty
from elfie.genesis.world import (
    WorldCanonPackage,
    WorldItemStatus,
    WorldKnowledgeFact,
    WorldPlace,
    WorldStoryEvent,
)
from elfie.profile import ELFARIA_CANON, WORLD_CANON_VERSION

from .config_store import ConfigStoreError
from .documents import (
    BundledConfigSource,
    ConfigDocumentError,
    ConfigDocumentId,
    resolve_bundled_config_root,
)


class WorldCanonError(ConfigDocumentError):
    """The bundled World Canon cannot cross the Genesis boundary."""


class BundledWorldCanonSource:
    """Load and semantically validate the one public World Canon package."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = resolve_bundled_config_root(root)

    def load(self) -> WorldCanonPackage:
        try:
            loaded = BundledConfigSource(self.root).load(ConfigDocumentId.WORLD_CANON)
        except (ConfigDocumentError, ConfigStoreError) as error:
            raise WorldCanonError(str(error)) from error
        try:
            package = _package(loaded.document)
            _validate_package(package)
            return package
        except (TypeError, ValueError, KeyError) as error:
            raise WorldCanonError(f"Elfaria World Canon 无效: {error}") from error


def load_world_canon(*, root: Path | None = None) -> WorldCanonPackage:
    """Load the immutable World Canon through the registered config boundary."""

    return BundledWorldCanonSource(root).load()


def _package(document: Mapping[str, Any]) -> WorldCanonPackage:
    region = _mapping(document["known_region"])
    relation = _mapping(document["earth_relation"])
    return WorldCanonPackage(
        version=_int(document, "version"),
        schema_version=_int(document, "schema_version"),
        canon_version=_text(document, "canon_version"),
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
    )


def _validate_package(package: WorldCanonPackage) -> None:
    if package.version != 1 or package.schema_version != 1:
        raise ValueError("只支持 World Canon v1")
    if package.world_id != ELFARIA_CANON.world_id:
        raise ValueError("world_id 与 Elfaria Canon 不一致")
    if package.display_name != ELFARIA_CANON.display_name:
        raise ValueError("display_name 与 Elfaria Canon 不一致")
    if package.canon_version != WORLD_CANON_VERSION:
        raise ValueError("canon_version 与 Elfaria Canon 不一致")
    if package.known_region_id != ELFARIA_CANON.known_region_id:
        raise ValueError("known_region.id 与 Elfaria Canon 不一致")
    if package.known_region_name != ELFARIA_CANON.known_region_name:
        raise ValueError("known_region.name 与 Elfaria Canon 不一致")
    if package.earth_home_name != ELFARIA_CANON.earth_home_name:
        raise ValueError("earth_home_name 与 Elfaria Canon 不一致")
    if (
        package.civilization_relation_to_earth
        != ELFARIA_CANON.civilization_relation_to_earth
    ):
        raise ValueError("civilization_relation_to_earth 与 Elfaria Canon 不一致")
    if package.earth_arrival_statement != ELFARIA_CANON.earth_arrival_statement:
        raise ValueError("earth_arrival_statement 与 Elfaria Canon 不一致")
    if package.earth_home_role != ELFARIA_CANON.earth_home_role:
        raise ValueError("earth_home_role 与 Elfaria Canon 不一致")

    place_ids = {place.place_id for place in package.places}
    if len(place_ids) != len(package.places):
        raise ValueError("World Canon place ID 必须唯一")
    required_place_ids = {
        "mistyville_square",
        "mistyville_homes",
        "mistyville_learning_house",
        "mistyville_waystation",
        "earth_gateway_station",
        "elfie_nest",
    }
    if not required_place_ids <= place_ids:
        missing = ", ".join(sorted(required_place_ids - place_ids))
        raise ValueError(f"World Canon 缺少首版地点: {missing}")
    allowed_parents = {package.world_id, package.known_region_id, *place_ids, "earth"}
    for place in package.places:
        if place.parent_id not in allowed_parents:
            raise ValueError(f"地点 {place.place_id} 的 parent_id 未定义")
        if place.parent_id == place.place_id:
            raise ValueError(f"地点 {place.place_id} 不能以自身为父节点")

    event_ids = {event.event_id for event in package.story_events}
    if len(event_ids) != len(package.story_events):
        raise ValueError("World Canon story event ID 必须唯一")
    required_event_ids = {
        "story_signal",
        "story_confirmation",
        "story_station",
        "story_program",
        "story_arrival",
    }
    if not required_event_ids <= event_ids:
        missing = ", ".join(sorted(required_event_ids - event_ids))
        raise ValueError(f"World Canon 缺少首版故事事件: {missing}")
    fact_ids = {fact.fact_id for fact in package.knowledge}
    if len(fact_ids) != len(package.knowledge):
        raise ValueError("World Canon knowledge ID 必须唯一")
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
        if not fact.source_ref.startswith("canon:"):
            raise ValueError(f"fact {fact.fact_id} 必须引用 canon source")
    for event in package.story_events:
        if not event.source_ref.startswith("canon:"):
            raise ValueError(f"story event {event.event_id} 必须引用 canon source")


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
    return value


def _int(document: Mapping[str, Any], key: str) -> int:
    value = document[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} 必须是整数")
    return value


def _optional_float(document: Mapping[str, Any], key: str, *, default: float) -> float:
    value = document.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 必须是数字")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{key} 必须在 [0, 1] 内")
    return result


def _texts(document: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = document[key]
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{key} 必须是字符串数组")
    return tuple(value)


def _status(document: Mapping[str, Any], key: str) -> WorldItemStatus:
    value = _text(document, key)
    if value not in ("active", "unknown-boundary"):
        raise ValueError(f"{key} 状态无效")
    return cast("WorldItemStatus", value)


__all__ = (
    "BundledWorldCanonSource",
    "WorldCanonError",
    "load_world_canon",
)
