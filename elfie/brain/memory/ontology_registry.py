"""Narrow internal port for controlled Memory ontology extensions."""

from __future__ import annotations

from typing import Literal, Protocol

from .ontology import EpisodeTypeSpec, NodeTypeSpec, OntologyStatus, PredicateSpec

OntologyEntryKind = Literal["node_type", "episode_type", "predicate"]


class MemoryOntologyRegistryPort(Protocol):
    """Persistence contract for the product-root-wide additive registry."""

    def propose_node_type(self, spec: NodeTypeSpec) -> int: ...

    def propose_episode_type(self, spec: EpisodeTypeSpec) -> int: ...

    def propose_predicate(self, spec: PredicateSpec) -> int: ...

    def set_extension_status(
        self,
        kind: OntologyEntryKind,
        key: str,
        status: OntologyStatus,
    ) -> int: ...


__all__ = ("MemoryOntologyRegistryPort", "OntologyEntryKind")
