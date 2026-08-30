"""Narrow storage contract shared by memory algorithms."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from .memory_records import (
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    ConsolidationReceipt,
    EpisodeReceipt,
    EvidenceInput,
    MaintenanceReceipt,
    MaintenanceRequest,
    NodeInput,
    RecallAssertion,
    RecallBundle,
    RecallNode,
    RecallRequest,
)


class MemoryStorePort(Protocol):
    """Semantic storage operations required by Brain memory algorithms."""

    def close(self) -> None: ...

    # Source-first contract. Episodes are the durable source line; graph
    # records and RecallBundle values are typed projections.
    def count_episodes(self, *, include_forgotten: bool = False) -> int: ...

    def count_graph_nodes(
        self,
        node_type: str | None = None,
        *,
        include_forgotten: bool = False,
    ) -> int: ...

    def count_memory_records(self, *, include_forgotten: bool = False) -> int: ...

    def upsert_node_record(self, node: NodeInput) -> str: ...

    def record_sourced_assertion(
        self,
        assertion: AssertionInput,
        evidence: EvidenceInput,
    ) -> str: ...

    def record_episode(self, episode: ClosedEpisode) -> EpisodeReceipt: ...

    def list_episodes(
        self, limit: int = 1000, *, include_forgotten: bool = False
    ) -> tuple[ClosedEpisode, ...]: ...

    def list_graph_nodes(
        self, limit: int = 1000, *, privacy_scope: str | None = None
    ) -> tuple[RecallNode, ...]: ...

    def get_graph_node(
        self, node_id: str, *, privacy_scope: str | None = None
    ) -> RecallNode | None: ...

    def list_graph_assertions(
        self, limit: int = 800, *, privacy_scope: str | None = None
    ) -> tuple[RecallAssertion, ...]: ...

    def get_episode(self, episode_id: str) -> ClosedEpisode | None: ...

    def pending_episodes(self, limit: int = 8) -> tuple[ClosedEpisode, ...]: ...

    def claim_episodes(
        self,
        limit: int = 8,
        *,
        owner: str = "memory-worker",
        lease_seconds: int = 120,
    ) -> tuple[ClosedEpisode, ...]: ...

    def mark_episode_failed(
        self,
        episode_id: str,
        error: str,
        *,
        owner: str | None = None,
        attempt: int | None = None,
    ) -> bool: ...

    def recover_expired_leases(self) -> int: ...

    def apply_consolidation(
        self, projection: ConsolidationProjection
    ) -> ConsolidationReceipt: ...

    def recall(self, request: RecallRequest) -> RecallBundle: ...

    def write_transaction(self) -> AbstractContextManager[None]: ...

    def run_lifecycle(
        self,
        request: MaintenanceRequest,
    ) -> MaintenanceReceipt: ...

    def has_due_lifecycle(self) -> bool: ...

    def recover_expired_maintenance_leases(self) -> int: ...

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
