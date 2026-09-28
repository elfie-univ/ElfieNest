"""Infrastructure validation and Bootstrap loading for the Memory ontology."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from elfie.brain.memory.ontology import (
    EpisodeTypeSpec,
    MemoryOntologyError,
    MemoryOntologySnapshot,
    NodeTypeGroup,
    NodeTypeSpec,
    OntologyStatus,
    PredicateSpec,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_bundled_document,
)
from infrastructure.persistence.configuration.documents import ConfigDocumentId

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def load_core_memory_ontology(
    *, config_root: Path | None = None
) -> MemoryOntologySnapshot:
    """Load and validate only the immutable bundled core vocabulary."""
    document = load_bundled_document(
        ConfigDocumentId.MEMORY_ONTOLOGY,
        root=config_root,
    )
    return parse_memory_ontology_document(document)


def load_memory_ontology_snapshot(
    *,
    data_home: Path | None = None,
    config_root: Path | None = None,
    registry_path: Path | None = None,
    include_extensions: bool = True,
) -> MemoryOntologySnapshot:
    """Capture a validated core-plus-registry snapshot for one product root."""
    document = load_bundled_document(
        ConfigDocumentId.MEMORY_ONTOLOGY,
        root=config_root,
    )
    core = parse_memory_ontology_document(document)
    if not include_extensions:
        return core

    if registry_path is None:
        if data_home is None:
            from infrastructure.persistence.layout.data_home import get_elfie_home

            data_home = get_elfie_home()
        from infrastructure.persistence.layout.data_layout import (
            ensure_final_root_layout,
        )

        registry_path = ensure_final_root_layout(
            Path(data_home)
        ).memory_ontology_database

    from infrastructure.persistence.memory.sqlite_ontology_registry import (
        SQLiteMemoryOntologyRegistryAdapter,
    )

    with SQLiteMemoryOntologyRegistryAdapter(registry_path, document) as registry:
        return registry.snapshot()


def parse_memory_ontology_document(
    document: Mapping[str, Any],
    *,
    registry_revision: int = 0,
    extensions: Sequence[tuple[str, str, OntologyStatus, Mapping[str, Any]]] = (),
) -> MemoryOntologySnapshot:
    """Validate a core YAML document and merge already-decoded extensions."""
    if document.get("version") != 1:
        raise MemoryOntologyError("Memory ontology version must be 1")
    core_revision = _text(document.get("core_revision"), "core_revision")

    raw_groups = _sequence(document.get("type_groups"), "type_groups")
    groups = tuple(_parse_group(raw) for raw in raw_groups)
    group_ids = tuple(group.group_id for group in groups)
    if len(set(group_ids)) != len(group_ids) or len(group_ids) != 5:
        raise MemoryOntologyError("core ontology must define five unique type groups")

    raw_node_types = _sequence(document.get("node_types"), "node_types")
    core_types = tuple(_parse_node_type(raw, core=True) for raw in raw_node_types)
    type_ids = tuple(spec.node_type for spec in core_types)
    if len(set(type_ids)) != len(type_ids):
        raise MemoryOntologyError("core ontology contains duplicate node types")
    if {spec.group_id for spec in core_types} != set(group_ids):
        raise MemoryOntologyError(
            "every core type group must contain at least one Node type"
        )

    raw_episode_types = _sequence(document.get("episode_types"), "episode_types")
    core_episode_types = tuple(
        _parse_episode_type(raw, core=True) for raw in raw_episode_types
    )
    _require_unique((item.event_kind for item in core_episode_types), "episode types")

    raw_predicates = _mapping(document.get("predicates"), "predicates")
    aliases_raw = _mapping(document.get("predicate_aliases", {}), "predicate_aliases")
    common_qualifiers = _string_tuple(
        document.get("common_qualifiers", ()), "common_qualifiers"
    )
    core_predicates = tuple(
        _parse_predicate(key, raw, common_qualifiers=common_qualifiers, core=True)
        for key, raw in raw_predicates.items()
    )
    _require_unique((item.predicate for item in core_predicates), "predicates")
    aliases = tuple(
        (
            _identifier(key, "predicate alias"),
            _identifier(value, "predicate alias target"),
        )
        for key, value in aliases_raw.items()
    )
    _require_unique((key for key, _ in aliases), "predicate aliases")

    node_types: list[NodeTypeSpec] = list(core_types)
    episode_types: list[EpisodeTypeSpec] = list(core_episode_types)
    predicates: list[PredicateSpec] = list(core_predicates)
    core_node_ids = {item.node_type for item in core_types}
    core_episode_ids = {item.event_kind for item in core_episode_types}
    core_predicate_ids = {item.predicate for item in core_predicates}
    for kind, key, status, definition in extensions:
        if kind == "node_type":
            node_spec = _parse_node_type(definition, core=False, status=status)
            if node_spec.node_type != key or key in core_node_ids:
                raise MemoryOntologyError(
                    f"extension shadows or mismatches core node type: {key}"
                )
            node_types.append(node_spec)
        elif kind == "episode_type":
            episode_spec = _parse_episode_type(definition, core=False, status=status)
            if episode_spec.event_kind != key or key in core_episode_ids:
                raise MemoryOntologyError(
                    f"extension shadows or mismatches core Episode type: {key}"
                )
            episode_types.append(episode_spec)
        elif kind == "predicate":
            predicate_spec = _parse_predicate(
                key,
                definition,
                common_qualifiers=common_qualifiers,
                core=False,
                status=status,
            )
            if key in core_predicate_ids:
                raise MemoryOntologyError(f"extension shadows core predicate: {key}")
            predicates.append(predicate_spec)
        else:
            raise MemoryOntologyError(f"unknown ontology extension kind: {kind}")

    _require_unique((item.node_type for item in node_types), "merged node types")
    _require_unique((item.event_kind for item in episode_types), "merged Episode types")
    _require_unique((item.predicate for item in predicates), "merged predicates")
    _validate_predicates(groups, node_types, predicates)

    predicate_ids = {item.predicate for item in predicates}
    for alias, target in aliases:
        if alias in predicate_ids or target not in predicate_ids:
            raise MemoryOntologyError(f"invalid predicate alias: {alias} -> {target}")

    return MemoryOntologySnapshot(
        core_revision=core_revision,
        registry_revision=registry_revision,
        type_groups=tuple(sorted(groups, key=lambda item: item.order)),
        node_types=tuple(node_types),
        episode_types=tuple(episode_types),
        predicates=tuple(predicates),
        predicate_aliases=aliases,
    )


def _parse_group(raw: Any) -> NodeTypeGroup:
    value = _mapping(raw, "type group")
    group_id = _identifier(value.get("id"), "type group id")
    label = _text(value.get("label"), f"{group_id}.label")
    color = _color(value.get("color"), f"{group_id}.color")
    order = value.get("order")
    if isinstance(order, bool) or not isinstance(order, int) or order < 1:
        raise MemoryOntologyError(f"{group_id}.order must be a positive integer")
    return NodeTypeGroup(group_id, label, color, order)


def _parse_node_type(
    raw: Any,
    *,
    core: bool,
    status: OntologyStatus = "active",
) -> NodeTypeSpec:
    value = _mapping(raw, "node type")
    key_field = "id" if core else "id"
    node_type = _identifier(value.get(key_field), "node type id")
    group_id = _identifier(value.get("group"), f"{node_type}.group")
    return NodeTypeSpec(
        node_type=node_type,
        label=_text(value.get("label"), f"{node_type}.label"),
        group_id=group_id,
        color=_color(value.get("color"), f"{node_type}.color"),
        status=status,
        core=core,
    )


def _parse_episode_type(
    raw: Any,
    *,
    core: bool,
    status: OntologyStatus = "active",
) -> EpisodeTypeSpec:
    value = _mapping(raw, "Episode type")
    return EpisodeTypeSpec(
        event_kind=_identifier(value.get("id"), "Episode type id"),
        label=_text(value.get("label"), "Episode type label"),
        status=status,
        core=core,
    )


def _parse_predicate(
    key: Any,
    raw: Any,
    *,
    common_qualifiers: tuple[str, ...],
    core: bool,
    status: OntologyStatus = "active",
) -> PredicateSpec:
    predicate = _identifier(key, "predicate id")
    value = _mapping(raw, f"predicate {predicate}")
    label = _text(value.get("label"), f"{predicate}.label")
    subject_groups = _identifier_tuple(
        value.get("subject_groups", ()), f"{predicate}.subject_groups"
    )
    subject_types = _identifier_tuple(
        value.get("subject_types", ()), f"{predicate}.subject_types"
    )
    object_groups = _identifier_tuple(
        value.get("object_groups", ()), f"{predicate}.object_groups"
    )
    object_types = _identifier_tuple(
        value.get("object_types", ()), f"{predicate}.object_types"
    )
    symmetric = _boolean(value.get("symmetric"), f"{predicate}.symmetric")
    inverse_value = value.get("inverse")
    inverse = (
        None
        if inverse_value is None
        else _identifier(inverse_value, f"{predicate}.inverse")
    )
    object_literal = _boolean(
        value.get("object_literal"), f"{predicate}.object_literal"
    )
    qualifiers = _string_tuple(
        value.get("qualifiers", common_qualifiers), f"{predicate}.qualifiers"
    )
    if len(set(qualifiers)) != len(qualifiers):
        raise MemoryOntologyError(f"{predicate}.qualifiers contains duplicates")
    source_required = _boolean(
        value.get("source_required"), f"{predicate}.source_required"
    )
    salience = value.get("salience")
    if (
        isinstance(salience, bool)
        or not isinstance(salience, (int, float))
        or not 0 <= salience <= 1
    ):
        raise MemoryOntologyError(f"{predicate}.salience must be between 0 and 1")
    self_stance = _boolean(value.get("self_stance", False), f"{predicate}.self_stance")
    if not (subject_groups or subject_types):
        raise MemoryOntologyError(
            f"{predicate} must constrain at least one subject group or type"
        )
    if not (object_groups or object_types) and not object_literal:
        raise MemoryOntologyError(
            f"{predicate} must constrain Node objects or allow literals"
        )
    return PredicateSpec(
        predicate=predicate,
        label=label,
        subject_groups=subject_groups,
        subject_types=subject_types,
        object_groups=object_groups,
        object_types=object_types,
        object_literal=object_literal,
        symmetric=symmetric,
        inverse=inverse,
        qualifiers=qualifiers,
        source_required=source_required,
        salience=float(salience),
        self_stance=self_stance,
        status=status,
        core=core,
    )


def _validate_predicates(
    groups: tuple[NodeTypeGroup, ...],
    node_types: list[NodeTypeSpec],
    predicates: list[PredicateSpec],
) -> None:
    group_ids = {item.group_id for item in groups}
    type_by_id = {item.node_type: item for item in node_types}
    predicate_by_id = {item.predicate: item for item in predicates}
    for node_spec in node_types:
        if node_spec.group_id not in group_ids:
            raise MemoryOntologyError(
                f"node type {node_spec.node_type!r} references unknown group {node_spec.group_id!r}"
            )
    for predicate_spec in predicates:
        for group_id in (
            *predicate_spec.subject_groups,
            *predicate_spec.object_groups,
        ):
            if group_id not in group_ids:
                raise MemoryOntologyError(
                    f"predicate {predicate_spec.predicate!r} references unknown group {group_id!r}"
                )
        for node_type in (
            *predicate_spec.subject_types,
            *predicate_spec.object_types,
        ):
            if node_type not in type_by_id:
                raise MemoryOntologyError(
                    f"predicate {predicate_spec.predicate!r} references unknown node type {node_type!r}"
                )
        if predicate_spec.status == "active":
            referenced_types = tuple(
                type_by_id[node_type]
                for node_type in (
                    *predicate_spec.subject_types,
                    *predicate_spec.object_types,
                )
            )
            if any(item.status != "active" for item in referenced_types):
                raise MemoryOntologyError(
                    f"active predicate {predicate_spec.predicate!r} references a non-active Node type"
                )
        if predicate_spec.self_stance and "elfie" not in predicate_spec.subject_types:
            raise MemoryOntologyError(
                f"self-stance predicate {predicate_spec.predicate!r} must allow the Elfie subject"
            )
        if predicate_spec.inverse is not None:
            reverse = predicate_by_id.get(predicate_spec.inverse)
            if reverse is None or reverse.inverse != predicate_spec.predicate:
                raise MemoryOntologyError(
                    f"predicate inverse must be reciprocal: {predicate_spec.predicate} <-> {predicate_spec.inverse}"
                )
            if predicate_spec.symmetric or reverse.symmetric:
                raise MemoryOntologyError(
                    "symmetric predicates cannot also declare inverses"
                )
            if predicate_spec.status == "active" and reverse.status != "active":
                raise MemoryOntologyError(
                    f"active predicate {predicate_spec.predicate!r} references a non-active inverse"
                )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise MemoryOntologyError(f"{name} must be a string-keyed mapping")
    return value


def _sequence(value: Any, name: str) -> tuple[Any, ...]:
    if not isinstance(value, (tuple, list)):
        raise MemoryOntologyError(f"{name} must be a list")
    return tuple(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryOntologyError(f"{name} must be a non-blank string")
    return value.strip()


def _identifier(value: Any, name: str) -> str:
    text = _text(value, name)
    if _IDENTIFIER.fullmatch(text) is None:
        raise MemoryOntologyError(f"{name} must be a lowercase identifier: {text!r}")
    return text


def _identifier_tuple(value: Any, name: str) -> tuple[str, ...]:
    values = tuple(_identifier(item, name) for item in _sequence(value, name))
    _require_unique(values, name)
    return values


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    values = tuple(_text(item, name) for item in _sequence(value, name))
    _require_unique(values, name)
    return values


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise MemoryOntologyError(f"{name} must be a boolean")
    return value


def _color(value: Any, name: str) -> str:
    text = _text(value, name)
    if _COLOR.fullmatch(text) is None:
        raise MemoryOntologyError(f"{name} must be a #RRGGBB color")
    return text.lower()


def _require_unique(values: Any, name: str) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise MemoryOntologyError(f"{name} contains duplicate identifiers")


__all__ = (
    "load_core_memory_ontology",
    "load_memory_ontology_snapshot",
    "parse_memory_ontology_document",
)
