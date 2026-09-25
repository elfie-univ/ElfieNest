"""Immutable, persistence-neutral snapshot of the Memory ontology."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OntologyStatus = Literal["candidate", "active", "deprecated"]


class MemoryOntologyError(ValueError):
    """A Memory record does not conform to the active ontology snapshot."""


@dataclass(frozen=True)
class NodeTypeGroup:
    group_id: str
    label: str
    color: str
    order: int


@dataclass(frozen=True)
class NodeTypeSpec:
    node_type: str
    label: str
    group_id: str
    color: str
    status: OntologyStatus = "active"
    core: bool = True


@dataclass(frozen=True)
class EpisodeTypeSpec:
    event_kind: str
    label: str
    status: OntologyStatus = "active"
    core: bool = True


@dataclass(frozen=True)
class PredicateSpec:
    predicate: str
    label: str
    subject_groups: tuple[str, ...]
    subject_types: tuple[str, ...]
    object_groups: tuple[str, ...]
    object_types: tuple[str, ...]
    object_literal: bool
    symmetric: bool
    inverse: str | None
    qualifiers: tuple[str, ...]
    source_required: bool
    salience: float
    self_stance: bool = False
    status: OntologyStatus = "active"
    core: bool = True


@dataclass(frozen=True)
class MemoryOntologySnapshot:
    """A fully validated core-plus-extension vocabulary captured at one revision.

    Tuples are intentional: this value crosses the Bootstrap → Brain boundary,
    and must not retain a mutable YAML dictionary or registry query result.
    """

    core_revision: str
    registry_revision: int
    type_groups: tuple[NodeTypeGroup, ...]
    node_types: tuple[NodeTypeSpec, ...]
    episode_types: tuple[EpisodeTypeSpec, ...]
    predicates: tuple[PredicateSpec, ...]
    predicate_aliases: tuple[tuple[str, str], ...] = ()

    @property
    def revision(self) -> str:
        return f"{self.core_revision}+registry:{self.registry_revision}"

    @property
    def self_stance_predicates(self) -> tuple[str, ...]:
        return tuple(
            spec.predicate
            for spec in self.predicates
            if spec.status == "active" and spec.self_stance
        )

    def group_for_node_type(self, node_type: str) -> str:
        """Return a registered active type's primary group."""
        spec = self.node_type_spec(node_type)
        if spec.status != "active":
            raise MemoryOntologyError(
                f"Memory node type {node_type!r} is {spec.status}, not writable"
            )
        return spec.group_id

    def node_type_spec(self, node_type: str) -> NodeTypeSpec:
        key = _normalize_key(node_type)
        spec = next((item for item in self.node_types if item.node_type == key), None)
        if spec is None:
            raise MemoryOntologyError(f"unsupported Memory node_type: {node_type}")
        return spec

    def active_node_types(
        self, group_id: str | None = None
    ) -> tuple[NodeTypeSpec, ...]:
        return tuple(
            spec
            for spec in self.node_types
            if spec.status == "active"
            and (group_id is None or spec.group_id == group_id)
        )

    def validate_node_type(self, node_type: str) -> NodeTypeSpec:
        spec = self.node_type_spec(node_type)
        if spec.status != "active":
            raise MemoryOntologyError(
                f"Memory node type {node_type!r} is {spec.status}, not writable"
            )
        return spec

    def validate_episode_type(self, event_kind: str) -> EpisodeTypeSpec:
        key = _normalize_key(event_kind)
        spec = next(
            (item for item in self.episode_types if item.event_kind == key), None
        )
        if spec is None:
            raise MemoryOntologyError(f"unsupported Episode event_kind: {event_kind}")
        if spec.status != "active":
            raise MemoryOntologyError(
                f"Episode event_kind {event_kind!r} is {spec.status}, not writable"
            )
        return spec

    def resolve_predicate(self, value: str) -> str:
        normalized = _normalize_key(value)
        aliases = dict(self.predicate_aliases)
        normalized = aliases.get(normalized, normalized)
        spec = next(
            (item for item in self.predicates if item.predicate == normalized), None
        )
        if spec is None or spec.status != "active":
            raise MemoryOntologyError(
                f"unknown or non-active predicate for ontology {self.revision}: {value}"
            )
        return normalized

    def predicate_spec(self, value: str) -> PredicateSpec:
        canonical = self.resolve_predicate(value)
        return next(item for item in self.predicates if item.predicate == canonical)

    def validate_assertion(
        self,
        *,
        predicate: str,
        subject_type: str,
        object_type: str | None,
        object_is_literal: bool,
        qualifiers: tuple[str, ...] = (),
        has_source: bool,
    ) -> PredicateSpec:
        """Validate a typed assertion against one immutable registry revision."""
        spec = self.predicate_spec(predicate)
        subject = self.validate_node_type(subject_type)
        if not _endpoint_matches(subject, spec.subject_groups, spec.subject_types):
            raise MemoryOntologyError(
                f"predicate {spec.predicate!r} does not allow subject type {subject_type!r}"
            )
        if object_is_literal:
            if not spec.object_literal:
                raise MemoryOntologyError(
                    f"predicate {spec.predicate!r} does not allow literal objects"
                )
        else:
            if object_type is None:
                raise MemoryOntologyError(
                    f"predicate {spec.predicate!r} requires a registered object Node"
                )
            object_node = self.validate_node_type(object_type)
            if not _endpoint_matches(
                object_node, spec.object_groups, spec.object_types
            ):
                raise MemoryOntologyError(
                    f"predicate {spec.predicate!r} does not allow object type {object_type!r}"
                )
        unknown_qualifiers = set(qualifiers) - set(spec.qualifiers)
        if unknown_qualifiers:
            raise MemoryOntologyError(
                f"predicate {spec.predicate!r} does not allow qualifiers: "
                + ", ".join(sorted(unknown_qualifiers))
            )
        if spec.source_required and not has_source:
            raise MemoryOntologyError(
                f"predicate {spec.predicate!r} requires source Evidence"
            )
        return spec


def _endpoint_matches(
    spec: NodeTypeSpec,
    groups: tuple[str, ...],
    node_types: tuple[str, ...],
) -> bool:
    return (not groups and not node_types) or (
        spec.group_id in groups or spec.node_type in node_types
    )


def _normalize_key(value: str) -> str:
    return "_".join(value.strip().casefold().replace("-", " ").split())


__all__ = (
    "EpisodeTypeSpec",
    "MemoryOntologyError",
    "MemoryOntologySnapshot",
    "NodeTypeGroup",
    "NodeTypeSpec",
    "OntologyStatus",
    "PredicateSpec",
)
