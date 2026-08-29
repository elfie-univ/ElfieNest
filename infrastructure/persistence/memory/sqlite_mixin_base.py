"""Shared type surface for the SQLite Memory mixins.

The concrete adapter is assembled from several focused mixins.  The mixins
call one another through that adapter, so this small base class declares the
cross-mixin surface once for static type checkers without adding another
runtime storage authority.
"""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from threading import RLock
from typing import Iterable

from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    ConsolidationProjection,
    ConsolidationReceipt,
    EpisodeReceipt,
    MaintenanceReceipt,
    MaintenanceRequest,
    NodeInput,
    RecallAssertion,
    RecallEvidence,
    RecallNode,
)
from elfie.brain.memory.node_types import Edge


class SQLiteMemoryMixinBase:
    """Declare the shared adapter members used by individual mixins."""

    conn: sqlite3.Connection
    _lock: RLock

    def _genesis_visibility(self, alias: str) -> tuple[str, list[object]]:
        """Return a marker-gated predicate for rows produced by Genesis."""
        raise NotImplementedError

    def upsert_node_record(self, node: NodeInput) -> str:
        raise NotImplementedError

    def get_edges(self, node_id: str, direction: str = "outgoing") -> list[Edge]:
        raise NotImplementedError

    def add_edge(
        self, source_id: str, target_id: str, rel: str, weight: float = 0.5
    ) -> str:
        raise NotImplementedError

    def record_episode(self, episode: ClosedEpisode) -> EpisodeReceipt:
        raise NotImplementedError

    def _upsert_episode_fts_from_values(
        self, episode_id: str, content: str, summary: str | None
    ) -> None:
        raise NotImplementedError

    def search_by_content(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
        *,
        privacy_scope: str | None = None,
    ) -> list[tuple[str, float]]:
        raise NotImplementedError

    def resolve_graph_node_id(self, node_id: str) -> str | None:
        raise NotImplementedError

    def get_graph_node(
        self, node_id: str, *, privacy_scope: str | None = None
    ) -> RecallNode | None:
        raise NotImplementedError

    def graph_assertions_for(
        self,
        node_ids: Iterable[str],
        *,
        relation_types: Iterable[str] = (),
        limit: int = 80,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
    ) -> tuple[RecallAssertion, ...]:
        raise NotImplementedError

    def get_assertion_evidence(
        self,
        assertion_ids: Iterable[str],
        limit: int = 24,
        *,
        privacy_scope: str | None = None,
    ) -> tuple[RecallEvidence, ...]:
        raise NotImplementedError

    def claim_episodes(
        self,
        limit: int = 8,
        *,
        owner: str = "memory-worker",
        lease_seconds: int = 120,
    ) -> tuple[ClosedEpisode, ...]:
        raise NotImplementedError

    def pending_episodes(self, limit: int = 8) -> tuple[ClosedEpisode, ...]:
        raise NotImplementedError

    def mark_episode_failed(self, episode_id: str, error: str) -> bool:
        raise NotImplementedError

    def apply_consolidation(
        self, projection: ConsolidationProjection
    ) -> ConsolidationReceipt:
        raise NotImplementedError

    def write_transaction(self) -> AbstractContextManager[None]:
        raise NotImplementedError

    def run_lifecycle(self, request: MaintenanceRequest) -> MaintenanceReceipt:
        raise NotImplementedError

    def inspect_episode(self, episode_id: str) -> ClosedEpisode | None:
        raise NotImplementedError

    def genesis_submission(
        self,
        *,
        submission_id: str,
        manifest_id: str,
        source_version: str,
        content_sha256: str,
        expected_ids: tuple[str, ...] = (),
        elfie_id: str | None = None,
    ) -> AbstractContextManager[bool]:
        raise NotImplementedError


__all__ = ("SQLiteMemoryMixinBase",)
