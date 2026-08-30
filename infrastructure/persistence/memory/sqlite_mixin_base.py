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
    RecallEvidence,
    RecallNode,
)


class SQLiteMemoryMixinBase:
    """Declare the shared adapter members used by individual mixins."""

    conn: sqlite3.Connection
    _lock: RLock
    elfie_id: str | None
    _active_genesis_submission_id: str | None
    _transaction_depth: int

    def _begin_write_transaction(self) -> bool:
        raise NotImplementedError

    def _commit_write_transaction(self, owns: bool) -> None:
        raise NotImplementedError

    def _rollback_write_transaction(self, owns: bool) -> None:
        raise NotImplementedError

    def _genesis_visibility(self, alias: str) -> tuple[str, list[object]]:
        """Return a marker-gated predicate for rows produced by Genesis."""
        raise NotImplementedError

    def upsert_node_record(self, node: NodeInput) -> str:
        raise NotImplementedError

    def record_sourced_assertion(
        self, assertion: AssertionInput, evidence: EvidenceInput
    ) -> str:
        raise NotImplementedError

    def record_episode(self, episode: ClosedEpisode) -> EpisodeReceipt:
        raise NotImplementedError

    def list_episodes(
        self, limit: int = 1000, *, include_forgotten: bool = False
    ) -> tuple[ClosedEpisode, ...]:
        raise NotImplementedError

    def list_graph_nodes(
        self, limit: int = 1000, *, privacy_scope: str | None = None
    ) -> tuple[RecallNode, ...]:
        raise NotImplementedError

    def list_graph_assertions(
        self, limit: int = 800, *, privacy_scope: str | None = None
    ) -> tuple[RecallAssertion, ...]:
        raise NotImplementedError

    def _upsert_episode_fts_from_values(
        self, episode_id: str, content: str, summary: str | None
    ) -> None:
        raise NotImplementedError

    def search_text(
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
        person_node_ids: Iterable[str] = (),
        place_node_ids: Iterable[str] = (),
        emotion_labels: Iterable[str] = (),
        topic_labels: Iterable[str] = (),
        cause_labels: Iterable[str] = (),
        privacy_scope: str | None = None,
        include_unknown_time: bool = False,
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

    def mark_episode_failed(
        self,
        episode_id: str,
        error: str,
        *,
        owner: str | None = None,
        attempt: int | None = None,
    ) -> bool:
        raise NotImplementedError

    def apply_consolidation(
        self, projection: ConsolidationProjection
    ) -> ConsolidationReceipt:
        raise NotImplementedError

    def write_transaction(self) -> AbstractContextManager[None]:
        raise NotImplementedError

    def run_lifecycle(self, request: MaintenanceRequest) -> MaintenanceReceipt:
        raise NotImplementedError

    def has_due_lifecycle(self) -> bool:
        raise NotImplementedError

    def recover_expired_maintenance_leases(self) -> int:
        raise NotImplementedError

    def inspect_episode(self, episode_id: str) -> ClosedEpisode | None:
        raise NotImplementedError

    def get_episode(self, episode_id: str) -> ClosedEpisode | None:
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
