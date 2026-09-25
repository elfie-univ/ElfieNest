"""Internal, non-HTTP application boundary for ontology curation."""

from __future__ import annotations

from elfie.brain.memory.ontology import (
    EpisodeTypeSpec,
    MemoryOntologyError,
    MemoryOntologySnapshot,
    NodeTypeSpec,
    PredicateSpec,
)
from elfie.brain.memory.ontology_registry import (
    MemoryOntologyRegistryPort,
    OntologyEntryKind,
)


class MemoryOntologyExtensionService:
    """Propose, activate, or deprecate additive vocabulary entries.

    This service is deliberately not exposed through Operations HTTP routes or
    any model-facing tool. A caller must be an explicitly trusted internal
    maintenance path.
    """

    def __init__(
        self,
        registry: MemoryOntologyRegistryPort,
        snapshot: MemoryOntologySnapshot,
    ) -> None:
        self._registry = registry
        self._snapshot = snapshot

    def propose_node_type(
        self,
        node_type: str,
        *,
        label: str,
        group_id: str,
        color: str,
    ) -> int:
        if not any(item.group_id == group_id for item in self._snapshot.type_groups):
            raise MemoryOntologyError(f"unknown core node type group: {group_id}")
        spec = NodeTypeSpec(
            node_type=node_type,
            label=label,
            group_id=group_id,
            color=color,
            status="candidate",
            core=False,
        )
        self._validate_new_identity(node_type)
        return self._registry.propose_node_type(spec)

    def propose_episode_type(self, event_kind: str, *, label: str) -> int:
        self._validate_new_identity(event_kind)
        return self._registry.propose_episode_type(
            EpisodeTypeSpec(
                event_kind=event_kind,
                label=label,
                status="candidate",
                core=False,
            )
        )

    def propose_predicate(self, spec: PredicateSpec) -> int:
        if spec.core or spec.status != "candidate":
            raise MemoryOntologyError("an extension predicate must start as candidate")
        self._validate_new_identity(spec.predicate)
        self._validate_predicate_endpoints(spec)
        return self._registry.propose_predicate(spec)

    def activate(self, kind: OntologyEntryKind, key: str) -> int:
        return self._registry.set_extension_status(kind, key, "active")

    def deprecate(self, kind: OntologyEntryKind, key: str) -> int:
        return self._registry.set_extension_status(kind, key, "deprecated")

    def _validate_new_identity(self, key: str) -> None:
        normalized = key.strip().casefold().replace("-", "_")
        if not normalized or any(character.isspace() for character in normalized):
            raise MemoryOntologyError("ontology key must be a non-blank identifier")

    def _validate_predicate_endpoints(self, spec: PredicateSpec) -> None:
        group_ids = {item.group_id for item in self._snapshot.type_groups}
        type_specs = {item.node_type: item for item in self._snapshot.node_types}
        for group_id in (*spec.subject_groups, *spec.object_groups):
            if group_id not in group_ids:
                raise MemoryOntologyError(
                    f"predicate {spec.predicate!r} references unknown group {group_id!r}"
                )
        for node_type in (*spec.subject_types, *spec.object_types):
            if node_type not in type_specs:
                raise MemoryOntologyError(
                    f"predicate {spec.predicate!r} references unknown node type {node_type!r}"
                )


__all__ = ("MemoryOntologyExtensionService",)
