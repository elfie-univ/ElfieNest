"""Narrow storage contract shared by memory algorithms."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Mapping, Protocol

from .memory_records import (
    ClosedEpisode,
    ConsolidationProjection,
    ConsolidationReceipt,
    EpisodeReceipt,
    MaintenanceReceipt,
    MaintenanceRequest,
    RecallBundle,
    RecallRequest,
)
from .node_types import Edge, JsonValue, MemoryMetadata, MemoryNode


class MemoryStorePort(Protocol):
    """Semantic storage operations required by Brain memory algorithms."""

    def add_node(self, node: MemoryNode) -> str: ...

    def get_node(self, node_id: str) -> MemoryNode | None: ...

    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        metadata: Mapping[str, JsonValue] | MemoryMetadata | None = None,
        edges: list[Edge] | None = None,
    ) -> bool: ...

    def delete_node(self, node_id: str) -> bool: ...

    def get_nodes_by_type(
        self, node_type: str, limit: int = 100
    ) -> list[MemoryNode]: ...

    def get_unconsolidated_nodes(
        self, node_type: str = "episodic"
    ) -> list[MemoryNode]: ...

    def count_nodes(self, node_type: str | None = None) -> int: ...

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        rel: str,
        weight: float = 0.5,
    ) -> str | int: ...

    def get_edges(self, node_id: str, direction: str = "outgoing") -> list[Edge]: ...

    def search_by_content(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
        *,
        privacy_scope: str | None = None,
    ) -> list[tuple[str, float]]: ...

    def close(self) -> None: ...

    # Target source-first contract. The legacy node methods above remain only
    # as a semantic compatibility surface for existing callers.
    def record_episode(self, episode: ClosedEpisode) -> EpisodeReceipt: ...

    def get_episode(self, episode_id: str) -> ClosedEpisode | None: ...

    def pending_episodes(self, limit: int = 8) -> tuple[ClosedEpisode, ...]: ...

    def claim_episodes(
        self,
        limit: int = 8,
        *,
        owner: str = "memory-worker",
        lease_seconds: int = 120,
    ) -> tuple[ClosedEpisode, ...]: ...

    def mark_episode_failed(self, episode_id: str, error: str) -> bool: ...

    def apply_consolidation(
        self, projection: ConsolidationProjection
    ) -> ConsolidationReceipt: ...

    def recall(self, request: RecallRequest) -> RecallBundle: ...

    def write_transaction(self) -> AbstractContextManager[None]: ...

    def run_lifecycle(
        self,
        request: MaintenanceRequest,
    ) -> MaintenanceReceipt: ...

    def inspect_episode(self, episode_id: str) -> ClosedEpisode | None: ...

    def genesis_submission(
        self,
        *,
        submission_id: str,
        manifest_id: str,
        source_version: str,
        content_sha256: str,
        expected_ids: tuple[str, ...] = (),
        elfie_id: str | None = None,
    ) -> AbstractContextManager[bool]: ...


__all__ = ["MemoryStorePort"]
