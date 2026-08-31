"""Graph projection and evidence operations for SQLite Memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from elfie.brain.memory.memory_records import (
    AliasInput,
    AssertionEvidenceInput,
    AssertionInput,
    ConsolidationProjection,
    ConsolidationReceipt,
    DescriptionInput,
    EvidenceInput,
    MentionInput,
    NodeInput,
    QualifiedReinforcementReceipt,
    RecallAssertion,
    RecallEvidence,
    RecallNode,
    RetentionClass,
)
from elfie.brain.memory.predicates import (
    PREDICATE_REGISTRY_VERSION,
    UnknownPredicateError,
    resolve_predicate,
)
from elfie.brain.memory.score_policy import (
    EvidenceContribution,
    ImportanceEvent,
    MemoryScorePolicy,
)

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import (
    bounded_score,
    canonical_json,
    content_hash,
    json_object,
    normalize_text,
    stable_id,
    utc_now,
)

_NON_CANONICAL_NODE_TYPES = frozenset({"event", "episode", "claim"})
_MAX_EPISODE_MENTIONS = 128
_SCORE_COMPACTION_MAX_TARGETS = 256
_SCORE_COMPACTION_SAFETY_DAYS = 2.0
_IMPORTANCE_WINDOW = timedelta(hours=24)


class SQLiteGraphStoreMixin(SQLiteMemoryMixinBase):
    conn: sqlite3.Connection

    def record_importance_event(self, event: ImportanceEvent) -> bool:
        """Atomically admit and fold one sourced semantic importance event.

        The row value is always rebuilt from the immutable admission baseline
        and all accepted events.  This keeps retries, duplicate delivery and
        out-of-order event arrival deterministic without introducing another
        score implementation in the adapter.
        """
        occurred_at = _timestamp_text(event.occurred_at)
        now = utc_now()
        MemoryScorePolicy.importance_event_policy(event.direction, event.event_class)
        MemoryScorePolicy.validate_event_time(now=now, occurred_at=occurred_at)
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                accepted = self._record_importance_event_locked(
                    replace(event, occurred_at=occurred_at), now
                )
                self._commit_write_transaction(owns)
                return accepted
            except Exception:
                self._rollback_write_transaction(owns)
                raise

    def _record_importance_event_locked(self, event: ImportanceEvent, now: str) -> bool:
        """Insert and fold one event while the caller owns the write UoW."""
        target = self._importance_target_locked(event.target_kind, event.target_id)
        if target is None:
            raise ValueError(
                f"unknown importance target: {event.target_kind}:{event.target_id}"
            )
        self._validate_event_source_locked(event.source_episode_id)
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        self._ensure_importance_baseline_locked(
            event.target_kind, event.target_id, target, now
        )
        checkpoint = self.conn.execute(
            """SELECT folded_through FROM memory_score_checkpoints
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='importance'""",
            (elfie_id, event.target_kind, event.target_id),
        ).fetchone()
        folded_through = None if checkpoint is None else checkpoint["folded_through"]
        existing = self.conn.execute(
            """SELECT direction, event_class, source_episode_id, occurred_at,
                              policy_version
                 FROM memory_importance_events
                WHERE elfie_id=? AND event_id=? AND target_kind=? AND target_id=?""",
            (elfie_id, event.event_id, event.target_kind, event.target_id),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != (
                event.direction,
                event.event_class,
                event.source_episode_id,
                str(event.occurred_at),
                MemoryScorePolicy.version,
            ):
                raise ValueError(
                    "importance event identity was reused with different content"
                )
            return False
        is_late = folded_through is not None and _parse_utc_timestamp(
            str(event.occurred_at)
        ) <= _parse_utc_timestamp(str(folded_through))
        self.conn.execute(
            """INSERT INTO memory_importance_events(
                   event_id, elfie_id, target_kind, target_id, direction,
                   event_class, source_episode_id, occurred_at,
                   policy_version, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                elfie_id,
                event.target_kind,
                event.target_id,
                event.direction,
                event.event_class,
                event.source_episode_id,
                str(event.occurred_at),
                MemoryScorePolicy.version,
                now,
            ),
        )
        if is_late:
            self._record_score_reconciliation_locked(
                target_kind=event.target_kind,
                target_id=event.target_id,
                score_kind="importance",
                reason="late_event_before_folded_watermark",
                payload={
                    "event_id": event.event_id,
                    "occurred_at": str(event.occurred_at),
                    "folded_through": str(folded_through),
                },
                now=now,
            )
            return False
        self._replay_importance_target_locked(event.target_kind, event.target_id, now)
        return True

    def consume_reinforcement_receipt(
        self, receipt: QualifiedReinforcementReceipt
    ) -> bool:
        """Consume one externally authorized, idempotent retention receipt."""
        occurred_at = _timestamp_text(receipt.occurred_at)
        now = utc_now()
        MemoryScorePolicy.validate_event_time(now=now, occurred_at=occurred_at)
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                accepted = self._reinforce_target_locked(
                    target_kind=receipt.target_kind,
                    target_id=receipt.target_id,
                    occurred_at=occurred_at,
                    source_ref=receipt.source_ref,
                    outcome_kind=receipt.outcome_kind,
                    now=now,
                    recall_revision=receipt.recall_revision,
                    receipt_id=receipt.event_id,
                )
                self._commit_write_transaction(owns)
                return accepted
            except Exception:
                self._rollback_write_transaction(owns)
                raise

    def compact_score_control(
        self,
        *,
        now: str | None = None,
        safety_window_days: float = _SCORE_COMPACTION_SAFETY_DAYS,
        max_targets: int = _SCORE_COMPACTION_MAX_TARGETS,
    ) -> dict[str, int]:
        """Fold only settled score-control prefixes into checkpoints.

        Score-control rows are operational audit data, not semantic Memory.
        A small late-arrival safety window keeps recent receipts individually
        replayable.  Older prefixes are folded into the target checkpoint and
        retained in the source table; they are never physically removed, so diagnostics
        can still inspect the bounded history and a late event can be routed
        to reconciliation instead of silently changing a score.
        """
        if safety_window_days < 0.0:
            raise ValueError("safety_window_days must not be negative")
        if max_targets < 1:
            return {
                "importance_targets": 0,
                "importance_events": 0,
                "retention_targets": 0,
                "retention_receipts": 0,
            }
        current = _timestamp_text(now or utc_now())
        cutoff = _parse_utc_timestamp(current) - timedelta(days=safety_window_days)
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                checkpoints = self.conn.execute(
                    """SELECT target_kind, target_id, score_kind
                         FROM memory_score_checkpoints
                        WHERE elfie_id=? AND score_kind IN ('importance', 'retention')
                        ORDER BY score_kind, target_kind, target_id LIMIT ?""",
                    (elfie_id, max_targets),
                ).fetchall()
                importance_target_count = 0
                importance_event_count = 0
                retention_target_count = 0
                retention_receipt_count = 0
                for checkpoint in checkpoints:
                    if str(checkpoint["score_kind"]) == "importance":
                        folded = self._compact_importance_checkpoint_locked(
                            target_kind=str(checkpoint["target_kind"]),
                            target_id=str(checkpoint["target_id"]),
                            now=current,
                            cutoff=cutoff,
                        )
                        if folded:
                            importance_target_count += 1
                            importance_event_count += folded
                    else:
                        folded = self._compact_retention_checkpoint_locked(
                            target_kind=str(checkpoint["target_kind"]),
                            target_id=str(checkpoint["target_id"]),
                            now=current,
                            cutoff=cutoff,
                        )
                        if folded:
                            retention_target_count += 1
                            retention_receipt_count += folded
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return {
            "importance_targets": importance_target_count,
            "importance_events": importance_event_count,
            "retention_targets": retention_target_count,
            "retention_receipts": retention_receipt_count,
        }

    def _compact_importance_checkpoint_locked(
        self,
        *,
        target_kind: str,
        target_id: str,
        now: str,
        cutoff: datetime,
    ) -> int:
        """Fold only complete 24-hour importance windows.

        Importance events remain in the audit table.  The checkpoint moves the
        replay baseline forward and the watermark keeps those rows out of the
        hot replay path.  A window whose next event could still arrive inside
        the 24-hour aggregation interval is left unfurled.
        """
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        checkpoint = self.conn.execute(
            """SELECT folded_through, state_json
                 FROM memory_score_checkpoints
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='importance'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        if checkpoint is None:
            return 0
        folded_through = checkpoint["folded_through"]
        rows = self.conn.execute(
            """SELECT event_id, target_kind, target_id, direction,
                              event_class, occurred_at, source_episode_id,
                              policy_version
                 FROM memory_importance_events
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                ORDER BY occurred_at, event_id""",
            (elfie_id, target_kind, target_id),
        ).fetchall()
        if folded_through is not None:
            watermark = _parse_utc_timestamp(str(folded_through))
            rows = [
                row
                for row in rows
                if _parse_utc_timestamp(str(row["occurred_at"])) > watermark
            ]
        if not rows:
            return 0
        events_by_direction: dict[str, list[sqlite3.Row]] = {
            "raise": [],
            "lower": [],
        }
        for row in rows:
            events_by_direction[str(row["direction"])].append(row)
        unsafe_starts: list[datetime] = []
        for direction_rows in events_by_direction.values():
            ordered = sorted(
                direction_rows,
                key=lambda row: (
                    _parse_utc_timestamp(str(row["occurred_at"])),
                    str(row["event_id"]),
                ),
            )
            index = 0
            while index < len(ordered):
                start = _parse_utc_timestamp(str(ordered[index]["occurred_at"]))
                end = index + 1
                while end < len(ordered):
                    candidate = _parse_utc_timestamp(str(ordered[end]["occurred_at"]))
                    if candidate < start + _IMPORTANCE_WINDOW:
                        end += 1
                        continue
                    break
                group = ordered[index:end]
                next_start = (
                    _parse_utc_timestamp(str(ordered[end]["occurred_at"]))
                    if end < len(ordered)
                    else None
                )
                group_safe = all(
                    _parse_utc_timestamp(str(item["occurred_at"])) <= cutoff
                    for item in group
                ) and (
                    (
                        next_start is not None
                        and next_start >= start + _IMPORTANCE_WINDOW
                    )
                    or (next_start is None and cutoff >= start + _IMPORTANCE_WINDOW)
                )
                if not group_safe:
                    unsafe_starts.append(start)
                index = end
        barrier = min(unsafe_starts) if unsafe_starts else None
        prefix = [
            row
            for row in rows
            if _parse_utc_timestamp(str(row["occurred_at"])) <= cutoff
            and (
                barrier is None
                or _parse_utc_timestamp(str(row["occurred_at"])) < barrier
            )
        ]
        if not prefix:
            return 0
        prefix_watermark = str(prefix[-1]["occurred_at"])
        state = json_object(checkpoint["state_json"])
        target = self._importance_target_locked(target_kind, target_id)
        if target is None:
            return 0
        base = float(state.get("base_importance", target["initial_importance"]))
        prefix_events = _importance_events_from_rows(prefix)
        base = MemoryScorePolicy.fold_importance(
            initial=base,
            events=prefix_events,
            target_kind=target_kind,
            target_id=target_id,
        )
        suffix = [
            row
            for row in rows
            if _parse_utc_timestamp(str(row["occurred_at"]))
            > _parse_utc_timestamp(prefix_watermark)
        ]
        current = MemoryScorePolicy.fold_importance(
            initial=base,
            events=_importance_events_from_rows(suffix),
            target_kind=target_kind,
            target_id=target_id,
        )
        folded_count = int(state.get("folded_event_count", 0) or 0) + len(prefix)
        folded_ids = list(state.get("folded_event_ids", []))
        folded_ids.extend(str(row["event_id"]) for row in prefix)
        # Retain only a bounded audit hash input; the source rows remain the
        # complete audit trail and can be inspected independently.
        folded_ids = folded_ids[-1024:]
        state.update(
            {
                "base_importance": base,
                "current_importance": current,
                "folded_event_count": folded_count,
                "folded_event_ids": folded_ids,
                "suffix_event_count": len(suffix),
                "folded_event_hash": _extend_fold_hash(
                    str(
                        state.get("folded_event_hash") or _empty_fold_hash("importance")
                    ),
                    _importance_fold_tokens(prefix),
                ),
                "last_event_time": prefix_watermark,
            }
        )
        self.conn.execute(
            """UPDATE memory_score_checkpoints
                  SET folded_through=?, state_json=?, event_count=?,
                      policy_version=?, updated_at=?
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='importance'""",
            (
                prefix_watermark,
                canonical_json(state),
                folded_count,
                MemoryScorePolicy.version,
                now,
                elfie_id,
                target_kind,
                target_id,
            ),
        )
        self._update_importance_target_locked(
            target_kind=target_kind,
            target_id=target_id,
            importance=current,
            now=now,
        )
        return len(prefix)

    def _compact_retention_checkpoint_locked(
        self,
        *,
        target_kind: str,
        target_id: str,
        now: str,
        cutoff: datetime,
    ) -> int:
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        checkpoint = self.conn.execute(
            """SELECT folded_through, state_json
                 FROM memory_score_checkpoints
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='retention'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        if checkpoint is None:
            return 0
        rows = self.conn.execute(
            """SELECT receipt_id, target_kind, target_id, occurred_at,
                              outcome_kind, source_ref, recall_revision,
                              policy_version
                 FROM memory_retention_receipts
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND state='accepted'
                ORDER BY occurred_at, receipt_id""",
            (elfie_id, target_kind, target_id),
        ).fetchall()
        prefix = [
            row
            for row in rows
            if _parse_utc_timestamp(str(row["occurred_at"])) <= cutoff
        ]
        if not prefix:
            return 0
        target = self._retention_target_locked(target_kind, target_id)
        if target is None:
            return 0
        state = json_object(checkpoint["state_json"])
        if checkpoint["folded_through"]:
            days = float(state.get("current_retention_days", 7.0))
            anchor = str(state.get("current_anchor") or now)
        else:
            days = float(state.get("base_retention_days", 7.0))
            anchor = str(state.get("base_anchor") or now)
        eligible = _retention_target_is_active(target_kind, target)
        for row in prefix:
            update = (
                MemoryScorePolicy.reinforce(
                    retention_days=days,
                    last_reinforced_at=anchor,
                    occurred_at=str(row["occurred_at"]),
                )
                if eligible
                else None
            )
            if update is not None:
                days = update.retention_days
                anchor = update.last_reinforced_at.isoformat(timespec="milliseconds")
        receipt_ids = tuple(str(row["receipt_id"]) for row in prefix)
        placeholders = ",".join("?" for _ in receipt_ids)
        self.conn.execute(
            f"UPDATE memory_retention_receipts SET state='folded', policy_version=? "
            f"WHERE elfie_id=? AND receipt_id IN ({placeholders})",
            (MemoryScorePolicy.version, elfie_id, *receipt_ids),
        )
        folded_count = int(state.get("folded_event_count", 0) or 0) + len(prefix)
        state.update(
            {
                "current_retention_days": days,
                "current_anchor": anchor,
                "folded_event_count": folded_count,
                "folded_event_hash": _extend_fold_hash(
                    str(
                        state.get("folded_event_hash") or _empty_fold_hash("retention")
                    ),
                    _retention_fold_tokens(prefix),
                ),
                "last_event_time": str(prefix[-1]["occurred_at"]),
            }
        )
        self.conn.execute(
            """UPDATE memory_score_checkpoints
                  SET folded_through=?, state_json=?, event_count=?,
                      policy_version=?, updated_at=?
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='retention'""",
            (
                str(prefix[-1]["occurred_at"]),
                canonical_json(state),
                folded_count,
                MemoryScorePolicy.version,
                now,
                elfie_id,
                target_kind,
                target_id,
            ),
        )
        next_review = MemoryScorePolicy.next_review_at(
            anchor, days, MemoryScorePolicy.active_freshness_threshold
        ).isoformat(timespec="milliseconds")
        self._update_retention_target_locked(
            target_kind=target_kind,
            target_id=target_id,
            retention_days=days,
            anchor=anchor,
            next_review=next_review,
            now=now,
        )
        # Re-run the still-unfolded suffix from the newly folded state so the
        # materialized target remains equivalent to a full replay.
        self._replay_retention_target_locked(target_kind, target_id, "", now)
        return len(prefix)

    def apply_consolidation(
        self, projection: ConsolidationProjection
    ) -> ConsolidationReceipt:
        with self._lock:
            episode_visibility, episode_visibility_params = self._genesis_visibility(
                "e"
            )
            episode_scope = ""
            episode_scope_params: list[object] = []
            if getattr(self, "elfie_id", None) is not None:
                episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                episode_scope_params.append(str(self.elfie_id))
            episode = self.conn.execute(
                "SELECT e.episode_id, e.content_sha256, e.source_version, "
                "e.occurred_from, "
                "e.projection_revision, e.projection_source_sha256, "
                "e.consolidation_state, e.lease_owner, e.lease_until, "
                "e.consolidation_attempts "
                "FROM episodes AS e WHERE e.episode_id=? AND "
                + episode_visibility
                + episode_scope,
                [
                    projection.episode_id,
                    *episode_visibility_params,
                    *episode_scope_params,
                ],
            ).fetchone()
            if episode is None:
                raise ValueError(f"unknown Episode: {projection.episode_id}")
            if (projection.claim_owner is None) != (projection.claim_attempt is None):
                raise ValueError(
                    "claim_owner and claim_attempt must be supplied together"
                )
            if (
                str(episode["consolidation_state"]) == "processing"
                and projection.claim_owner is None
            ):
                raise ValueError("processing Episode requires a consolidation claim")
            if projection.claim_owner is not None:
                if (
                    str(episode["lease_owner"] or "") != projection.claim_owner
                    or int(episode["consolidation_attempts"] or 0)
                    != projection.claim_attempt
                    or episode["lease_until"] is None
                    or str(episode["lease_until"]) <= utc_now()
                ):
                    raise ValueError("stale consolidation claim")
            expected_hash = projection.source_sha256 or str(episode["content_sha256"])
            if expected_hash != str(episode["content_sha256"]):
                raise ValueError("projection source hash is stale")
            if (
                projection.source_version is not None
                and projection.source_version != episode["source_version"]
            ):
                raise ValueError("projection source version is stale")
            # Bind omitted provenance fields to the current source so a
            # first attempt and a retry that supplies the explicit hash/version
            # resolve to the same deterministic projection revision.
            projection = replace(
                projection,
                source_version=(
                    projection.source_version
                    if projection.source_version is not None
                    else episode["source_version"]
                ),
                source_sha256=expected_hash,
            )
            computed_revision = _projection_revision(projection)
            if (
                projection.projection_revision is not None
                and projection.projection_revision != computed_revision
            ):
                raise ValueError(
                    "projection_revision does not match projection content"
                )
            projection_revision = computed_revision
            if (
                episode["projection_revision"] == projection_revision
                and episode["projection_source_sha256"] == expected_hash
            ):
                return ConsolidationReceipt(
                    episode_id=projection.episode_id,
                    status="duplicate",
                )
            now = utc_now()
            evidence_by_id: dict[str, EvidenceInput] = {}
            node_id_map: dict[str, str] = {}
            assertion_ids: dict[str, str] = {}
            importance_targets: list[tuple[str, str, str]] = []
            mentions_truncated = False
            owns = self._begin_write_transaction()
            try:
                for evidence in projection.evidence:
                    if (
                        evidence.source_type == "episode"
                        and evidence.source_id != projection.episode_id
                    ):
                        raise ValueError(
                            "Episode evidence must point to the projected Episode"
                        )
                    self._insert_evidence(evidence, now)
                    evidence_by_id[evidence.evidence_id] = evidence
                for node in projection.nodes:
                    resolved_node_id = self._resolve_projection_node(node, now)
                    node_id_map[node.node_id] = resolved_node_id
                    if node.importance_event_class is not None:
                        importance_targets.append(
                            ("node", resolved_node_id, node.importance_event_class)
                        )
                for alias in projection.aliases:
                    resolved_alias_node_id: str | None = node_id_map.get(alias.node_id)
                    if resolved_alias_node_id is None:
                        resolved_alias_node_id = self._resolve_graph_node_id_locked(
                            alias.node_id
                        )
                    if resolved_alias_node_id is None:
                        raise ValueError(f"unknown node in alias: {alias.node_id}")
                    self._insert_alias(
                        AliasInput(
                            node_id=resolved_alias_node_id,
                            alias=alias.alias,
                            scope=alias.scope,
                            evidence_id=alias.evidence_id,
                            confidence=alias.confidence,
                        ),
                        now,
                    )
                for description in projection.descriptions:
                    resolved_description_node_id: str | None = node_id_map.get(
                        description.node_id
                    )
                    if resolved_description_node_id is None:
                        resolved_description_node_id = (
                            self._resolve_graph_node_id_locked(description.node_id)
                        )
                    if resolved_description_node_id is None:
                        raise ValueError(
                            f"unknown node in description: {description.node_id}"
                        )
                    self._insert_description(
                        DescriptionInput(
                            node_id=resolved_description_node_id,
                            text=description.text,
                            language=description.language,
                            kind=description.kind,
                            evidence_id=description.evidence_id,
                            confidence=description.confidence,
                        ),
                        now,
                    )

                existing_mention_keys = {
                    (str(row[0]), row[1], row[2])
                    for row in self.conn.execute(
                        "SELECT surface_text, span_start, span_end FROM episode_mentions WHERE episode_id=?",
                        (projection.episode_id,),
                    ).fetchall()
                }
                for mention in projection.mentions:
                    if mention.episode_id != projection.episode_id:
                        raise ValueError(
                            "projection mentions must belong to the projected Episode"
                        )
                    key = (
                        mention.surface_text.strip(),
                        mention.span_start,
                        mention.span_end,
                    )
                    if (
                        key not in existing_mention_keys
                        and len(existing_mention_keys) >= _MAX_EPISODE_MENTIONS
                    ):
                        mentions_truncated = True
                        continue
                    resolved_mention_node_id: str | None = (
                        node_id_map.get(mention.node_id)
                        if mention.node_id is not None
                        else None
                    )
                    if mention.node_id is not None and resolved_mention_node_id is None:
                        resolved_mention_node_id = self._resolve_graph_node_id_locked(
                            mention.node_id
                        )
                    if mention.node_id is not None and resolved_mention_node_id is None:
                        raise ValueError(f"unknown node in mention: {mention.node_id}")
                    self._insert_mention(
                        MentionInput(
                            episode_id=mention.episode_id,
                            surface_text=mention.surface_text,
                            node_id=resolved_mention_node_id,
                            resolution_state=mention.resolution_state,
                            role=mention.role,
                            span_start=mention.span_start,
                            span_end=mention.span_end,
                            confidence=mention.confidence,
                            evidence_id=(
                                mention.evidence_id
                                or _episode_evidence_id(self.conn, mention.episode_id)
                            ),
                        ),
                        now,
                    )
                    existing_mention_keys.add(key)

                for assertion in projection.assertions:
                    try:
                        canonical_predicate = resolve_predicate(assertion.predicate)
                    except UnknownPredicateError:
                        raise
                    if not assertion.evidence_ids:
                        raise ValueError(
                            "durable assertions require at least one evidence ID"
                        )
                    subject_id = node_id_map.get(assertion.subject_id)
                    if subject_id is None:
                        subject_id = self._resolve_graph_node_id_locked(
                            assertion.subject_id
                        )
                    if subject_id is None:
                        raise ValueError(
                            f"unknown assertion subject: {assertion.subject_id}"
                        )
                    object_node_reference = assertion.object_node_id
                    object_node_id = object_node_reference
                    if object_node_reference is not None:
                        object_node_id = node_id_map.get(object_node_reference)
                        if object_node_id is None:
                            object_node_id = self._resolve_graph_node_id_locked(
                                object_node_reference
                            )
                        if object_node_id is None:
                            raise ValueError(
                                f"unknown assertion object: {assertion.object_node_id}"
                            )
                    normalized_assertion = AssertionInput(
                        subject_id=subject_id,
                        predicate=canonical_predicate,
                        object_node_id=object_node_id,
                        object_literal=assertion.object_literal,
                        object_unit=assertion.object_unit,
                        polarity=assertion.polarity,
                        epistemic_status=assertion.epistemic_status,
                        viewpoint=assertion.viewpoint,
                        context=assertion.context,
                        valid_from=assertion.valid_from,
                        valid_to=assertion.valid_to,
                        confidence=assertion.confidence,
                        initial_confidence=assertion.initial_confidence,
                        prior_weight=assertion.prior_weight,
                        conflict_group=assertion.conflict_group,
                        supersedes_assertion_id=assertion.supersedes_assertion_id,
                        evidence_ids=assertion.evidence_ids,
                        assertion_id=assertion.assertion_id,
                        importance=assertion.importance,
                        initial_importance=assertion.initial_importance,
                        retention_days=assertion.retention_days,
                        retention_class=assertion.retention_class,
                        importance_event_class=assertion.importance_event_class,
                        object_literal_type=assertion.object_literal_type,
                        predicate_registry_version=PREDICATE_REGISTRY_VERSION,
                        policy_version=assertion.policy_version,
                        genesis_submission_id=assertion.genesis_submission_id,
                    )
                    if (
                        normalized_assertion.context == "correction"
                        and normalized_assertion.supersedes_assertion_id is None
                    ):
                        prior = self._latest_active_claim(
                            subject_id=subject_id,
                            predicate=normalized_assertion.predicate,
                            object_node_id=object_node_id,
                            object_literal=normalized_assertion.object_literal,
                            object_literal_type=normalized_assertion.object_literal_type,
                        )
                        if prior is not None:
                            normalized_assertion = AssertionInput(
                                subject_id=normalized_assertion.subject_id,
                                predicate=normalized_assertion.predicate,
                                object_node_id=normalized_assertion.object_node_id,
                                object_literal=normalized_assertion.object_literal,
                                object_unit=normalized_assertion.object_unit,
                                polarity=normalized_assertion.polarity,
                                epistemic_status=normalized_assertion.epistemic_status,
                                viewpoint=normalized_assertion.viewpoint,
                                context=normalized_assertion.context,
                                valid_from=normalized_assertion.valid_from,
                                valid_to=normalized_assertion.valid_to,
                                confidence=normalized_assertion.confidence,
                                initial_confidence=normalized_assertion.initial_confidence,
                                prior_weight=normalized_assertion.prior_weight,
                                conflict_group=normalized_assertion.conflict_group,
                                supersedes_assertion_id=prior,
                                evidence_ids=normalized_assertion.evidence_ids,
                                assertion_id=normalized_assertion.assertion_id,
                                importance=normalized_assertion.importance,
                                initial_importance=normalized_assertion.initial_importance,
                                retention_days=normalized_assertion.retention_days,
                                retention_class=normalized_assertion.retention_class,
                                importance_event_class=normalized_assertion.importance_event_class,
                                object_literal_type=normalized_assertion.object_literal_type,
                                predicate_registry_version=normalized_assertion.predicate_registry_version,
                                policy_version=normalized_assertion.policy_version,
                                genesis_submission_id=normalized_assertion.genesis_submission_id,
                            )
                    assertion_id = self._insert_assertion(normalized_assertion, now)
                    assertion_ids[assertion.assertion_id or assertion_id] = assertion_id
                    if normalized_assertion.importance_event_class is not None:
                        importance_targets.append(
                            (
                                "assertion",
                                assertion_id,
                                normalized_assertion.importance_event_class,
                            )
                        )
                    superseded_id = normalized_assertion.supersedes_assertion_id
                    if superseded_id is not None:
                        if superseded_id == assertion_id:
                            raise ValueError("an assertion cannot supersede itself")
                        if not self._assertion_exists(superseded_id):
                            raise ValueError(
                                f"unknown superseded assertion: {superseded_id}"
                            )
                    for evidence_id in assertion.evidence_ids:
                        if (
                            evidence_id not in evidence_by_id
                            and not self.conn.execute(
                                "SELECT 1 FROM evidence WHERE evidence_id=?",
                                (evidence_id,),
                            ).fetchone()
                        ):
                            raise ValueError(
                                f"unknown evidence for assertion: {evidence_id}"
                            )
                        self._insert_assertion_evidence(
                            AssertionEvidenceInput(
                                assertion_id=assertion_id,
                                evidence_id=evidence_id,
                            ),
                            assertion_id,
                            now,
                        )
                    if superseded_id is not None:
                        # A correction is both new support for the replacement
                        # claim and an auditable contradiction of the former
                        # claim.  Link the same source Evidence to the old
                        # Assertion while it is still active so its confidence
                        # is recomputed and its retention can be reinforced by
                        # the correction event.  The subsequent status change
                        # only affects availability; it never rewrites I/D/C.
                        if normalized_assertion.context == "correction":
                            for evidence_id in assertion.evidence_ids:
                                self._insert_assertion_evidence(
                                    AssertionEvidenceInput(
                                        assertion_id=superseded_id,
                                        evidence_id=evidence_id,
                                        stance="contradicts",
                                    ),
                                    superseded_id,
                                    now,
                                )
                        self.conn.execute(
                            "UPDATE assertions SET lifecycle='superseded', "
                            "lifecycle_changed_at=?, next_review_at=NULL, updated_at=? "
                            "WHERE assertion_id=? AND "
                            + self._assertion_namespace_predicate("assertions"),
                            (
                                now,
                                now,
                                superseded_id,
                                *self._assertion_namespace_params(),
                            ),
                        )

                for link in projection.assertion_evidence:
                    assertion_id = assertion_ids.get(
                        link.assertion_id, link.assertion_id
                    )
                    if not self._assertion_exists(assertion_id):
                        raise ValueError(
                            f"unknown assertion in evidence link: {assertion_id}"
                        )
                    if (
                        link.evidence_id not in evidence_by_id
                        and not self.conn.execute(
                            "SELECT 1 FROM evidence WHERE evidence_id=?",
                            (link.evidence_id,),
                        ).fetchone()
                    ):
                        raise ValueError(
                            f"unknown evidence in assertion link: {link.evidence_id}"
                        )
                    self._insert_assertion_evidence(link, assertion_id, now)

                # A model appraisal is a sourced semantic event, not a
                # caller-controlled numeric score.  Record and fold it only
                # after every projected target exists, still inside this same
                # transaction so a failed projection cannot leave a partial
                # importance update behind.
                event_time = str(episode["occurred_from"] or now)
                for target_kind, target_id, event_class in importance_targets:
                    self._record_importance_event_locked(
                        ImportanceEvent(
                            event_id=stable_id(
                                "importance-event:projection",
                                projection.episode_id,
                                projection_revision,
                                target_kind,
                                target_id,
                                event_class,
                                length=48,
                            ),
                            target_kind=target_kind,
                            target_id=target_id,
                            direction="raise",
                            event_class=event_class,
                            occurred_at=event_time,
                            source_episode_id=projection.episode_id,
                        ),
                        now,
                    )

                consolidation_sql = """UPDATE episodes SET consolidation_state='consolidated',
                           lease_owner=NULL, lease_until=NULL, next_attempt_at=NULL,
                           updated_at=? WHERE episode_id=?"""
                consolidation_params: list[object] = [now, projection.episode_id]
                if getattr(self, "elfie_id", None) is not None:
                    consolidation_sql += (
                        " AND json_extract(metadata_json, '$.elfie_id')=?"
                    )
                    consolidation_params.append(str(self.elfie_id))
                if projection.claim_owner is not None:
                    consolidation_sql += (
                        " AND consolidation_state='processing'"
                        " AND lease_owner=?"
                        " AND consolidation_attempts=?"
                        " AND lease_until>?"
                    )
                    consolidation_params.extend(
                        (projection.claim_owner, projection.claim_attempt, now)
                    )
                consolidation_cursor = self.conn.execute(
                    consolidation_sql,
                    consolidation_params,
                )
                if consolidation_cursor.rowcount != 1:
                    raise ValueError("stale consolidation claim")
                self.conn.execute(
                    """UPDATE episodes SET projection_revision=?,
                           projection_source_sha256=content_sha256,
                           updated_at=? WHERE episode_id=?"""
                    + (
                        " AND json_extract(metadata_json, '$.elfie_id')=?"
                        if getattr(self, "elfie_id", None) is not None
                        else ""
                    ),
                    (
                        projection_revision,
                        now,
                        projection.episode_id,
                        *(
                            (str(self.elfie_id),)
                            if getattr(self, "elfie_id", None) is not None
                            else ()
                        ),
                    ),
                )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                # A nested projection failure rolls back the complete outer
                # Unit of Work as well.  Persist the bounded diagnostic after
                # that rollback in either case, while leaving fact rows
                # unpublished and retryable.
                self._record_projection_diagnostic(
                    projection,
                    reason="projection_validation_failed",
                )
                raise
        return ConsolidationReceipt(
            episode_id=projection.episode_id,
            status="consolidated",
            nodes_created=len(projection.nodes),
            assertions_created=len(projection.assertions),
            evidence_created=len(projection.evidence),
            mentions_truncated=mentions_truncated,
        )

    def upsert_node_record(self, node: NodeInput) -> str:
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                self._upsert_node(node, utc_now())
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return node.node_id

    def merge_graph_nodes(self, source_id: str, target_id: str) -> bool:
        """Merge one identity into another without losing source evidence.

        Mentions are retargeted.  Assertions are either retargeted in place or
        folded into an existing qualified assertion while their evidence links
        remain attached.  The source node itself is retained as a merge
        pointer, so old IDs continue to resolve after a restart.
        """
        if source_id == target_id:
            return False
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                source = self.conn.execute(
                    "SELECT node_id, canonical_label FROM nodes WHERE node_id=?",
                    (source_id,),
                ).fetchone()
                target_root = self._resolve_graph_node_id_locked(target_id)
                source_root = self._resolve_graph_node_id_locked(source_id)
                if source is None or target_root is None or source_root != source_id:
                    self._commit_write_transaction(owns)
                    return False
                if target_root == source_id:
                    raise ValueError("node merge would create an identity cycle")
                now = utc_now()

                # Keep one canonical target for all historical mentions.
                self.conn.execute(
                    "UPDATE episode_mentions SET node_id=? WHERE node_id=?",
                    (target_root, source_id),
                )

                # Copy the old spelling into the target's aliases before the
                # source is hidden from normal search.
                self._insert_alias(
                    AliasInput(
                        node_id=target_root,
                        alias=str(source["canonical_label"]),
                        confidence=1.0,
                    ),
                    now,
                )

                # Move assertion endpoints.  A qualified duplicate is folded
                # into its canonical row; all evidence links are copied first.
                rows = self.conn.execute(
                    "SELECT * FROM assertions WHERE subject_node_id=? OR object_node_id=?",
                    (source_id, source_id),
                ).fetchall()
                for row in rows:
                    new_subject = (
                        target_root
                        if row["subject_node_id"] == source_id
                        else row["subject_node_id"]
                    )
                    new_object = (
                        target_root
                        if row["object_node_id"] == source_id
                        else row["object_node_id"]
                    )
                    assertion_input = _row_as_assertion_input(
                        row, new_subject, new_object
                    )
                    fingerprint = _assertion_fingerprint(assertion_input)
                    duplicate = self.conn.execute(
                        "SELECT assertion_id FROM assertions WHERE fingerprint=? AND assertion_id<>?",
                        (fingerprint, row["assertion_id"]),
                    ).fetchone()
                    if duplicate is not None:
                        self.conn.execute(
                            """INSERT INTO assertion_evidence(assertion_id, evidence_id, stance, created_at)
                               SELECT ?, evidence_id, stance, ? FROM assertion_evidence
                                WHERE assertion_id=?
                               ON CONFLICT(assertion_id, evidence_id) DO UPDATE SET
                                   stance=CASE
                                       WHEN assertion_evidence.stance=excluded.stance
                                           THEN assertion_evidence.stance
                                       ELSE 'context'
                                   END""",
                            (duplicate["assertion_id"], now, row["assertion_id"]),
                        )
                        self.conn.execute(
                            "UPDATE assertions SET lifecycle='superseded', updated_at=? WHERE assertion_id=?",
                            (now, row["assertion_id"]),
                        )
                    else:
                        self.conn.execute(
                            "UPDATE assertions SET subject_node_id=?, object_node_id=?, fingerprint=?, updated_at=? WHERE assertion_id=?",
                            (
                                new_subject,
                                new_object,
                                fingerprint,
                                now,
                                row["assertion_id"],
                            ),
                        )
                self.conn.execute(
                    "UPDATE nodes SET merged_into=?, updated_at=? WHERE node_id=?",
                    (target_root, now, source_id),
                )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return True

    def resolve_graph_node_id(self, node_id: str) -> str | None:
        """Follow bounded merge pointers without exposing SQL to Brain code."""
        with self._lock:
            return self._resolve_graph_node_id_locked(node_id)

    def _resolve_graph_node_id_locked(self, node_id: str) -> str | None:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            visibility, visibility_params = self._genesis_visibility("n")
            namespace_clause = ""
            namespace_params: list[object] = []
            if getattr(self, "elfie_id", None) is not None:
                namespace_clause = (
                    " AND json_extract(n.properties_json, '$.elfie_id')=?"
                )
                namespace_params.append(str(self.elfie_id))
            row = self.conn.execute(
                "SELECT n.node_id, n.merged_into FROM nodes AS n WHERE n.node_id=?"
                + namespace_clause
                + " AND "
                + visibility,
                [current, *namespace_params, *visibility_params],
            ).fetchone()
            if row is None:
                return None
            if row["merged_into"] is None:
                return str(row["node_id"])
            current = str(row["merged_into"])
        return None

    def get_graph_node(
        self,
        node_id: str,
        *,
        privacy_scope: str | None = None,
        now: str | None = None,
    ) -> Optional[RecallNode]:
        resolved = self.resolve_graph_node_id(node_id)
        if resolved is None:
            return None
        with self._lock:
            scope = ""
            params: list[object] = [resolved]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(properties_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            if privacy_scope is not None:
                scope += " AND n.privacy_scope=?"
                params.append(privacy_scope)
            visibility, visibility_params = self._genesis_visibility("n")
            params.extend(visibility_params)
            row = self.conn.execute(
                """SELECT node_id, node_type, canonical_label, description,
                          confidence, importance, retention_days, last_reinforced_at,
                          updated_at, properties_json FROM nodes AS n WHERE n.node_id=?
                          AND n.status IN ('active', 'candidate', 'unresolved')"""
                + scope
                + " AND "
                + visibility,
                params,
            ).fetchone()
        if row is None:
            return None
        return _row_to_recall_node(row, now=now or utc_now())

    def list_graph_nodes(
        self, limit: int = 100, *, privacy_scope: str | None = None
    ) -> tuple[RecallNode, ...]:
        with self._lock:
            scope = ""
            params: list[object] = [max(0, limit)]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                params = [str(self.elfie_id), max(0, limit)]
            if privacy_scope is not None:
                scope += " AND n.privacy_scope=?"
                params.insert(-1, privacy_scope)
            visibility, visibility_params = self._genesis_visibility("n")
            params[-1:-1] = visibility_params
            rows = self.conn.execute(
                """SELECT n.node_id, n.node_type, n.canonical_label, n.description,
                          n.confidence, n.importance, n.retention_days,
                          n.last_reinforced_at, n.updated_at, n.properties_json FROM nodes AS n WHERE n.status <> 'forgotten'
                                              AND n.merged_into IS NULL"""
                + scope
                + " AND "
                + visibility
                + " ORDER BY n.node_id LIMIT ?",
                params,
            ).fetchall()
        now = utc_now()
        return tuple(_row_to_recall_node(row, now=now) for row in rows)

    def find_graph_nodes(
        self, query: str, limit: int = 20, *, privacy_scope: str | None = None
    ) -> tuple[RecallNode, ...]:
        normalized = normalize_text(query)
        if not normalized:
            return ()
        like = f"%{normalized}%"
        with self._lock:
            scope = ""
            params: list[object] = [normalized, normalized, like, like]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            if privacy_scope is not None:
                scope += " AND n.privacy_scope=?"
                params.append(privacy_scope)
            visibility, visibility_params = self._genesis_visibility("n")
            params.extend(visibility_params)
            params.extend([like, like, like])
            params.append(max(0, limit))
            rows = self.conn.execute(
                """SELECT DISTINCT n.node_id, n.node_type, n.canonical_label,
                          n.description, n.confidence, n.importance, n.retention_days,
                          n.last_reinforced_at, n.updated_at, n.properties_json,
                          CASE WHEN n.normalized_label=? OR a.normalized_alias=? THEN 1.0
                               WHEN n.normalized_label LIKE ? THEN 0.8
                               WHEN a.normalized_alias LIKE ? THEN 0.75
                               ELSE 0.5 END AS score
                     FROM nodes AS n LEFT JOIN node_aliases AS a ON a.node_id=n.node_id
                    WHERE n.status IN ('active', 'candidate', 'unresolved') AND n.merged_into IS NULL"""
                + scope
                + " AND "
                + visibility
                + """
                      AND (n.normalized_label LIKE ? OR a.normalized_alias LIKE ?
                           OR lower(COALESCE(n.description,'')) LIKE ?)
                    ORDER BY score DESC, n.node_id LIMIT ?""",
                params,
            ).fetchall()
        now = utc_now()
        return tuple(
            _row_to_recall_node(row, relevance_key="score", now=now) for row in rows
        )

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
        now: str | None = None,
    ) -> tuple[RecallAssertion, ...]:
        ids = tuple(
            dict.fromkeys(
                resolved
                for node_id in node_ids
                if (resolved := self.resolve_graph_node_id(node_id)) is not None
            )
        )
        if not ids or limit < 1:
            return ()
        placeholders = ",".join("?" for _ in ids)
        relations = tuple(dict.fromkeys(relation_types))
        relation_clause = ""
        assertion_visibility, assertion_visibility_params = self._genesis_visibility(
            "a"
        )
        # Keep endpoint parameters separate from the shared predicates.  The
        # old ``subject IN (...) OR object IN (...)`` form encouraged SQLite
        # to walk the global lifecycle index and sort the entire assertion
        # table before it could apply the seed.  Two bounded endpoint queries
        # can use the subject/object indexes and the union is still complete:
        # the global top ``limit`` rows must be in the top ``limit`` rows of at
        # least one endpoint side.
        common_params: list[Any] = list(assertion_visibility_params)
        namespace_clause = ""
        if getattr(self, "elfie_id", None) is not None or privacy_scope is not None:
            namespace_conditions = ["ns.node_id=a.subject_node_id"]
            if getattr(self, "elfie_id", None) is not None:
                namespace_conditions.append(
                    "json_extract(ns.properties_json, '$.elfie_id')=?"
                )
                common_params.append(str(self.elfie_id))
            if privacy_scope is not None:
                namespace_conditions.append("ns.privacy_scope=?")
                common_params.append(privacy_scope)
            namespace_clause = (
                " AND EXISTS (SELECT 1 FROM nodes AS ns WHERE "
                + " AND ".join(namespace_conditions)
                + ")"
            )
            object_conditions: list[str] = []
            if getattr(self, "elfie_id", None) is not None:
                object_conditions.append(
                    "json_extract(no.properties_json, '$.elfie_id')=?"
                )
                common_params.append(str(self.elfie_id))
            if privacy_scope is not None:
                object_conditions.append("no.privacy_scope=?")
                common_params.append(privacy_scope)
            if object_conditions:
                namespace_clause += (
                    " AND (a.object_node_id IS NULL OR EXISTS ("
                    "SELECT 1 FROM nodes AS no WHERE no.node_id=a.object_node_id AND "
                    + " AND ".join(object_conditions)
                    + "))"
                )
        if relations:
            relation_clause = (
                " AND a.predicate IN (" + ",".join("?" for _ in relations) + ")"
            )
            common_params.extend(relations)
        time_clause = ""
        if (
            occurred_from is not None
            or occurred_to is not None
            or person_node_ids
            or place_node_ids
            or emotion_labels
            or topic_labels
            or cause_labels
            or privacy_scope is not None
        ):
            episode_conditions = ["p.lifecycle='active'"]
            time_params: list[Any] = []
            time_conditions: list[str] = []
            if occurred_from is not None:
                time_conditions.append(
                    "(p.occurred_from >= ? OR "
                    "(p.occurrence_precision='range' AND p.occurred_to >= ?))"
                )
                time_params.extend((occurred_from, occurred_from))
            if occurred_to is not None:
                time_conditions.append(
                    "p.occurred_from IS NOT NULL AND p.occurred_from <= ?"
                )
                time_params.append(occurred_to)
            if time_conditions:
                time_expression = " AND ".join(time_conditions)
                episode_conditions.append(
                    "(p.occurred_from IS NULL OR (" + time_expression + "))"
                    if include_unknown_time
                    else time_expression
                )
            facet_conditions, facet_params = _episode_facet_conditions(
                person_node_ids=person_node_ids,
                place_node_ids=place_node_ids,
                emotion_labels=emotion_labels,
                topic_labels=topic_labels,
                cause_labels=cause_labels,
                privacy_scope=privacy_scope,
            )
            episode_conditions.extend(facet_conditions)
            time_clause = (
                " AND EXISTS (SELECT 1 FROM assertion_evidence AS ae_time "
                "JOIN evidence AS e ON e.evidence_id=ae_time.evidence_id "
                "LEFT JOIN episodes AS p ON p.episode_id=e.source_id "
                "WHERE ae_time.assertion_id=a.assertion_id AND ("
                + "e.source_type <> 'episode' OR ("
                + " AND ".join(episode_conditions)
                + ")))"
            )
            common_params.extend(time_params)
            common_params.extend(facet_params)
        endpoint_clauses = (
            f"a.subject_node_id IN ({placeholders})",
            f"a.object_node_id IN ({placeholders})",
        )
        # SQL cannot see the derived freshness value without turning a local
        # graph hop into a table-wide calculation.  Oversample each indexed
        # endpoint, then decode and rank the bounded union with the v2 policy
        # so a stale high-importance row cannot evict a fresh lower-I claim.
        fetch_limit = min(800, max(limit * 4, limit + 1))
        with self._lock:
            rows_by_id: dict[str, sqlite3.Row] = {}
            for endpoint_clause in endpoint_clauses:
                rows = self.conn.execute(
                    f"""SELECT a.*,
                               COALESCE((SELECT group_concat(evidence_id, ',')
                                           FROM (SELECT ae.evidence_id
                                                   FROM assertion_evidence AS ae
                                                  WHERE ae.assertion_id=a.assertion_id
                                                  ORDER BY ae.evidence_id)), '')
                                   AS evidence_ids_csv
                             FROM assertions AS a
                        WHERE a.lifecycle IN ('active', 'superseded')
                          AND {endpoint_clause}
                          AND {assertion_visibility}
                          {namespace_clause}
                          {relation_clause}
                          {time_clause}
                        ORDER BY CASE WHEN a.lifecycle='active' THEN 0 ELSE 1 END,
                                 a.importance DESC, a.confidence DESC, a.assertion_id
                        LIMIT ?""",
                    list(ids) + common_params + [fetch_limit],
                ).fetchall()
                for row in rows:
                    rows_by_id.setdefault(str(row["assertion_id"]), row)
            assertion_rows: tuple[sqlite3.Row, ...] = tuple(rows_by_id.values())
        current_now = now or utc_now()
        decoded = tuple(
            _row_to_assertion(row, now=current_now) for row in assertion_rows
        )
        return tuple(
            sorted(
                decoded,
                key=lambda item: (
                    -item.relevance,
                    0 if item.status == "active" else 1,
                    -item.importance,
                    -item.confidence,
                    item.assertion_id,
                ),
            )[:limit]
        )

    def list_graph_assertions(
        self, limit: int = 800, *, privacy_scope: str | None = None
    ) -> tuple[RecallAssertion, ...]:
        """Return a bounded typed view of all visible graph assertions.

        The normal Recall path remains seed-driven.  This helper is reserved
        for authorized diagnostics and therefore walks the existing typed
        assertion query in bounded chunks instead of exposing SQL or adding a
        second retrieval implementation.
        """
        bounded_limit = max(0, min(int(limit), 5000))
        if bounded_limit == 0:
            return ()
        node_ids = tuple(
            node.node_id
            for node in self.list_graph_nodes(limit=10_000, privacy_scope=privacy_scope)
        )
        if not node_ids:
            return ()
        assertions: dict[str, RecallAssertion] = {}
        for start in range(0, len(node_ids), 500):
            remaining = bounded_limit - len(assertions)
            if remaining <= 0:
                break
            chunk = node_ids[start : start + 500]
            for assertion in self.graph_assertions_for(
                chunk,
                limit=remaining,
                privacy_scope=privacy_scope,
            ):
                assertions.setdefault(assertion.assertion_id, assertion)
        return tuple(
            sorted(
                assertions.values(),
                key=lambda item: (
                    0 if item.status == "active" else 1,
                    -item.importance,
                    -item.confidence,
                    item.assertion_id,
                ),
            )[:bounded_limit]
        )

    def get_assertion_evidence(
        self,
        assertion_ids: Iterable[str],
        limit: int = 24,
        *,
        privacy_scope: str | None = None,
    ) -> tuple[RecallEvidence, ...]:
        ids = tuple(dict.fromkeys(assertion_ids))
        if not ids or limit < 1:
            return ()
        placeholders = ",".join("?" for _ in ids)
        evidence_visibility, evidence_visibility_params = self._genesis_visibility("e")
        assertion_visibility, assertion_visibility_params = self._genesis_visibility(
            "a"
        )
        link_visibility, link_visibility_params = self._genesis_visibility("ae")
        assertion_namespace_clause = ""
        assertion_namespace_params: list[object] = []
        if getattr(self, "elfie_id", None) is not None or privacy_scope is not None:
            assertion_namespace_conditions = ["an.node_id=a.subject_node_id"]
            if getattr(self, "elfie_id", None) is not None:
                assertion_namespace_conditions.append(
                    "json_extract(an.properties_json, '$.elfie_id')=?"
                )
                assertion_namespace_params.append(str(self.elfie_id))
            if privacy_scope is not None:
                assertion_namespace_conditions.append("an.privacy_scope=?")
                assertion_namespace_params.append(privacy_scope)
            assertion_namespace_clause = (
                " AND EXISTS (SELECT 1 FROM nodes AS an WHERE "
                + " AND ".join(assertion_namespace_conditions)
                + ")"
            )
        privacy_clause = ""
        privacy_params: list[object] = []
        if privacy_scope is not None:
            privacy_clause = (
                " AND (e.source_type <> 'episode' OR EXISTS ("
                "SELECT 1 FROM episodes AS p WHERE p.episode_id=e.source_id "
                "AND p.lifecycle='active' AND p.privacy_scope=?))"
            )
            privacy_params.append(privacy_scope)
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT e.evidence_id, e.source_type, e.source_id, e.source_version,
                           e.excerpt, e.media_locator, e.modality, e.span_start,
                           e.span_end, e.speaker, e.viewpoint, e.captured_at,
                           e.attribution, e.independence_key,
                           e.source_reliability_class, e.source_policy_version,
                           CASE
                               WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                AND SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                   THEN 'context'
                               WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                   THEN 'supports'
                               WHEN SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                   THEN 'contradicts'
                               ELSE 'context'
                           END AS stance
                      FROM evidence AS e
                      JOIN assertion_evidence AS ae ON ae.evidence_id=e.evidence_id
                      JOIN assertions AS a ON a.assertion_id=ae.assertion_id
                     WHERE ae.assertion_id IN ({placeholders})
                       AND {evidence_visibility}
                       AND {assertion_visibility}
                       {assertion_namespace_clause}
                       AND {link_visibility}
                       {privacy_clause}
                     GROUP BY e.evidence_id, e.source_type, e.source_id, e.source_version,
                              e.excerpt, e.media_locator, e.modality, e.span_start,
                              e.span_end, e.speaker, e.viewpoint, e.captured_at,
                              e.attribution, e.independence_key,
                              e.source_reliability_class, e.source_policy_version
                     ORDER BY e.evidence_id LIMIT ?""",
                list(ids)
                + evidence_visibility_params
                + assertion_visibility_params
                + assertion_namespace_params
                + link_visibility_params
                + privacy_params
                + [max(0, limit)],
            ).fetchall()
        unique: dict[str, RecallEvidence] = {}
        for row in rows:
            evidence_id = str(row["evidence_id"])
            unique.setdefault(
                evidence_id,
                RecallEvidence(
                    evidence_id=evidence_id,
                    source_type=str(row["source_type"]),
                    source_id=str(row["source_id"]),
                    source_version=row["source_version"],
                    excerpt=row["excerpt"],
                    media_locator=row["media_locator"],
                    stance=str(row["stance"]),
                    modality=str(row["modality"]),
                    span_start=row["span_start"],
                    span_end=row["span_end"],
                    speaker=row["speaker"],
                    viewpoint=row["viewpoint"],
                    captured_at=row["captured_at"],
                    attribution=row["attribution"],
                    independence_key=row["independence_key"],
                    source_reliability_class=str(
                        row["source_reliability_class"] or "observed"
                    ),
                    source_policy_version=str(
                        row["source_policy_version"] or MemoryScorePolicy.version
                    ),
                ),
            )
        return tuple(unique.values())

    def get_evidence(self, evidence_id: str) -> Optional[RecallEvidence]:
        evidence_visibility, evidence_visibility_params = self._genesis_visibility("e")
        namespace_clause = ""
        namespace_params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            namespace_clause = (
                " AND ((e.source_type='episode' AND EXISTS ("
                "SELECT 1 FROM episodes AS source_e "
                "WHERE source_e.episode_id=e.source_id "
                "AND json_extract(source_e.metadata_json, '$.elfie_id')=?))"
                " OR (e.source_type<>'episode' AND EXISTS ("
                "SELECT 1 FROM assertion_evidence AS source_ae "
                "JOIN assertions AS source_a ON source_a.assertion_id=source_ae.assertion_id "
                "JOIN nodes AS source_n ON source_n.node_id=source_a.subject_node_id "
                "WHERE source_ae.evidence_id=e.evidence_id "
                "AND json_extract(source_n.properties_json, '$.elfie_id')=?)))"
            )
            namespace_params.extend([str(self.elfie_id), str(self.elfie_id)])
        with self._lock:
            row = self.conn.execute(
                """SELECT e.evidence_id, e.source_type, e.source_id, e.source_version,
                          e.excerpt, e.media_locator, e.modality, e.span_start,
                          e.span_end, e.speaker, e.viewpoint, e.captured_at, e.attribution,
                          e.independence_key, e.source_reliability_class,
                          e.source_policy_version,
                          CASE
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                               AND SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                  THEN 'context'
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                   THEN 'supports'
                              WHEN SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                  THEN 'contradicts'
                              WHEN COUNT(ae.stance) > 0 THEN 'context'
                              ELSE 'supports'
                          END AS stance
                     FROM evidence AS e LEFT JOIN assertion_evidence AS ae
                       ON ae.evidence_id=e.evidence_id
                    WHERE e.evidence_id=? AND """
                + evidence_visibility
                + namespace_clause
                + """
                     GROUP BY e.evidence_id, e.source_type, e.source_id, e.source_version,
                              e.excerpt, e.media_locator, e.modality, e.span_start,
                              e.span_end, e.speaker, e.viewpoint, e.captured_at,
                              e.attribution, e.independence_key,
                              e.source_reliability_class, e.source_policy_version""",
                [evidence_id, *evidence_visibility_params, *namespace_params],
            ).fetchone()
        if row is None:
            return None
        return RecallEvidence(
            evidence_id=str(row["evidence_id"]),
            source_type=str(row["source_type"]),
            source_id=str(row["source_id"]),
            source_version=row["source_version"],
            excerpt=row["excerpt"],
            media_locator=row["media_locator"],
            stance=str(row["stance"]),
            modality=str(row["modality"]),
            span_start=row["span_start"],
            span_end=row["span_end"],
            speaker=row["speaker"],
            viewpoint=row["viewpoint"],
            captured_at=row["captured_at"],
            attribution=row["attribution"],
            independence_key=row["independence_key"],
            source_reliability_class=str(row["source_reliability_class"] or "observed"),
            source_policy_version=str(
                row["source_policy_version"] or MemoryScorePolicy.version
            ),
        )

    def get_assertion_evidence_for_ids(
        self, evidence_ids: Iterable[str]
    ) -> tuple[RecallEvidence, ...]:
        ids = tuple(dict.fromkeys(evidence_ids))
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        evidence_visibility, evidence_visibility_params = self._genesis_visibility("e")
        link_visibility, link_visibility_params = self._genesis_visibility("ae")
        namespace_clause = ""
        namespace_params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            namespace_clause = (
                " AND ((e.source_type='episode' AND EXISTS ("
                "SELECT 1 FROM episodes AS source_e "
                "WHERE source_e.episode_id=e.source_id "
                "AND json_extract(source_e.metadata_json, '$.elfie_id')=?))"
                " OR (e.source_type<>'episode' AND EXISTS ("
                "SELECT 1 FROM assertion_evidence AS source_ae "
                "JOIN assertions AS source_a ON source_a.assertion_id=source_ae.assertion_id "
                "JOIN nodes AS source_n ON source_n.node_id=source_a.subject_node_id "
                "WHERE source_ae.evidence_id=e.evidence_id "
                "AND json_extract(source_n.properties_json, '$.elfie_id')=?)))"
            )
            namespace_params.extend([str(self.elfie_id), str(self.elfie_id)])
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT e.evidence_id, e.source_type, e.source_id, e.source_version,
                          e.excerpt, e.media_locator, e.modality, e.span_start,
                          e.span_end, e.speaker, e.viewpoint, e.captured_at, e.attribution,
                          e.independence_key, e.source_reliability_class,
                          e.source_policy_version,
                          CASE
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                               AND SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                  THEN 'context'
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                   THEN 'supports'
                               WHEN SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                   THEN 'contradicts'
                               WHEN COUNT(ae.stance) > 0 THEN 'context'
                               ELSE 'supports'
                           END AS stance
                      FROM evidence AS e LEFT JOIN assertion_evidence AS ae
                        ON ae.evidence_id=e.evidence_id
                     WHERE e.evidence_id IN ({placeholders})
                       AND {evidence_visibility}
                       AND {link_visibility}
                       {namespace_clause}
                     GROUP BY e.evidence_id, e.source_type, e.source_id, e.source_version,
                              e.excerpt, e.media_locator, e.modality, e.span_start,
                              e.span_end, e.speaker, e.viewpoint, e.captured_at,
                              e.attribution, e.independence_key,
                              e.source_reliability_class, e.source_policy_version
                     ORDER BY e.evidence_id""",
                list(ids)
                + evidence_visibility_params
                + link_visibility_params
                + namespace_params,
            ).fetchall()
        return tuple(
            RecallEvidence(
                evidence_id=str(row["evidence_id"]),
                source_type=str(row["source_type"]),
                source_id=str(row["source_id"]),
                source_version=row["source_version"],
                excerpt=row["excerpt"],
                media_locator=row["media_locator"],
                stance=str(row["stance"]),
                modality=str(row["modality"]),
                span_start=row["span_start"],
                span_end=row["span_end"],
                speaker=row["speaker"],
                viewpoint=row["viewpoint"],
                captured_at=row["captured_at"],
                attribution=row["attribution"],
                independence_key=row["independence_key"],
                source_reliability_class=str(
                    row["source_reliability_class"] or "observed"
                ),
                source_policy_version=str(
                    row["source_policy_version"] or MemoryScorePolicy.version
                ),
            )
            for row in rows
        )

    def record_sourced_assertion(
        self,
        assertion: AssertionInput,
        evidence: EvidenceInput,
        *,
        stance: str = "supports",
    ) -> str:
        """Write one already-qualified assertion for import/seed adapters."""
        if evidence.evidence_id not in assertion.evidence_ids:
            assertion = AssertionInput(
                subject_id=assertion.subject_id,
                predicate=assertion.predicate,
                object_node_id=assertion.object_node_id,
                object_literal=assertion.object_literal,
                object_unit=assertion.object_unit,
                polarity=assertion.polarity,
                epistemic_status=assertion.epistemic_status,
                viewpoint=assertion.viewpoint,
                context=assertion.context,
                valid_from=assertion.valid_from,
                valid_to=assertion.valid_to,
                confidence=assertion.confidence,
                initial_confidence=assertion.initial_confidence,
                prior_weight=assertion.prior_weight,
                conflict_group=assertion.conflict_group,
                supersedes_assertion_id=assertion.supersedes_assertion_id,
                evidence_ids=tuple(assertion.evidence_ids) + (evidence.evidence_id,),
                assertion_id=assertion.assertion_id,
                importance=assertion.importance,
                initial_importance=assertion.initial_importance,
                retention_days=assertion.retention_days,
                retention_class=assertion.retention_class,
                importance_event_class=assertion.importance_event_class,
                object_literal_type=assertion.object_literal_type,
                predicate_registry_version=assertion.predicate_registry_version,
                policy_version=assertion.policy_version,
                genesis_submission_id=assertion.genesis_submission_id,
            )
        with self._lock:
            now = utc_now()
            owns = self._begin_write_transaction()
            try:
                if self._resolve_graph_node_id_locked(assertion.subject_id) is None:
                    raise ValueError(
                        f"unknown assertion subject: {assertion.subject_id}"
                    )
                if (
                    assertion.object_node_id is not None
                    and self._resolve_graph_node_id_locked(assertion.object_node_id)
                    is None
                ):
                    raise ValueError(
                        f"unknown assertion object: {assertion.object_node_id}"
                    )
                self._insert_evidence(evidence, now)
                assertion_id = self._insert_assertion(assertion, now)
                self._insert_assertion_evidence(
                    AssertionEvidenceInput(
                        assertion_id=assertion_id,
                        evidence_id=evidence.evidence_id,
                        stance=stance,  # type: ignore[arg-type]
                    ),
                    assertion_id,
                    now,
                )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return assertion_id

    def _resolve_projection_node(self, node: NodeInput, now: str) -> str:
        """Resolve a proposed semantic node to one canonical identity.

        Event/claim nodes are intentionally episode-scoped and are never
        merged by label.  Reusable semantic anchors are matched by canonical
        label or an unambiguous alias within the same type and scope.  An
        ambiguous surface creates the proposed candidate instead of silently
        choosing one existing identity.
        """
        requested = self._resolve_graph_node_id_locked(node.node_id)
        if requested is not None:
            existing = self.conn.execute(
                "SELECT node_type, normalized_label, scope, properties_json FROM nodes WHERE node_id=?",
                (requested,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"resolved node disappeared: {requested}")
            if (
                str(existing["node_type"]) != node.node_type
                or str(existing["scope"]) != node.scope
                or str(existing["normalized_label"])
                != normalize_text(node.canonical_label)
            ):
                raise ValueError(
                    f"node ID is already bound to another identity: {node.node_id}"
                )
            self._upsert_node(
                NodeInput(
                    node_id=requested,
                    node_type=node.node_type,
                    canonical_label=node.canonical_label,
                    description=node.description,
                    scope=node.scope,
                    status=node.status,
                    confidence=node.confidence,
                    initial_confidence=node.initial_confidence,
                    prior_weight=node.prior_weight,
                    importance=node.importance,
                    initial_importance=node.initial_importance,
                    retention_days=node.retention_days,
                    retention_class=node.retention_class,
                    importance_event_class=node.importance_event_class,
                    properties=node.properties,
                ),
                now,
            )
            return requested

        normalized = normalize_text(node.canonical_label)
        if node.node_type not in _NON_CANONICAL_NODE_TYPES:
            namespace_clause = ""
            namespace_params: tuple[object, ...] = ()
            if getattr(self, "elfie_id", None) is not None:
                namespace_clause = (
                    " AND json_extract(n.properties_json, '$.elfie_id')=?"
                )
                namespace_params = (str(self.elfie_id),)
            rows = self.conn.execute(
                """SELECT n.node_id FROM nodes AS n
                   WHERE normalized_label=? AND node_type=? AND scope=?
                     AND status <> 'forgotten' AND merged_into IS NULL
                     """
                + namespace_clause
                + """
                   ORDER BY node_id LIMIT 2""",
                (normalized, node.node_type, node.scope, *namespace_params),
            ).fetchall()
            alias_rows = self.conn.execute(
                """SELECT DISTINCT n.node_id FROM node_aliases AS a
                   JOIN nodes AS n ON n.node_id=a.node_id
                  WHERE a.normalized_alias=? AND a.scope=?
                    AND n.node_type=? AND n.status <> 'forgotten'
                    AND n.merged_into IS NULL
                    """
                + namespace_clause
                + """
                  ORDER BY n.node_id LIMIT 2""",
                (normalized, node.scope, node.node_type, *namespace_params),
            ).fetchall()
            candidates = {str(row[0]) for row in rows}
            candidates.update(str(row[0]) for row in alias_rows)
            if len(candidates) == 1:
                resolved = next(iter(candidates))
                existing = self.conn.execute(
                    "SELECT canonical_label FROM nodes WHERE node_id=?", (resolved,)
                ).fetchone()
                canonical_label = (
                    str(existing["canonical_label"])
                    if existing is not None
                    else node.canonical_label
                )
                self._upsert_node(
                    NodeInput(
                        node_id=resolved,
                        node_type=node.node_type,
                        canonical_label=canonical_label,
                        description=node.description,
                        scope=node.scope,
                        status=node.status,
                        confidence=node.confidence,
                        initial_confidence=node.initial_confidence,
                        prior_weight=node.prior_weight,
                        importance=node.importance,
                        initial_importance=node.initial_importance,
                        retention_days=node.retention_days,
                        retention_class=node.retention_class,
                        importance_event_class=node.importance_event_class,
                        properties=node.properties,
                    ),
                    now,
                )
                return resolved

        self._upsert_node(node, now)
        return node.node_id

    def _upsert_node(self, node: NodeInput, now: str) -> None:
        label = node.canonical_label.strip()
        if not label:
            raise ValueError("node label must not be blank")
        existing = self.conn.execute(
            "SELECT node_type, normalized_label, scope, properties_json, description, "
            "first_seen_at, genesis_submission_id, initial_confidence, prior_weight, "
            "importance, initial_importance, retention_days, last_reinforced_at, "
            "last_reviewed_at, next_review_at, lifecycle_changed_at "
            "FROM nodes WHERE node_id=?",
            (node.node_id,),
        ).fetchone()
        if existing is not None and (
            str(existing["node_type"]) != node.node_type
            or str(existing["normalized_label"]) != normalize_text(label)
            or str(existing["scope"]) != node.scope
        ):
            raise ValueError(
                f"node ID is already bound to another identity: {node.node_id}"
            )
        properties = json_object(existing["properties_json"]) if existing else {}
        configured_elfie = getattr(self, "elfie_id", None)
        if configured_elfie is not None:
            existing_elfie = properties.get("elfie_id")
            if existing is not None and existing_elfie is None:
                raise ValueError(
                    "Node belongs to an unbound namespace and cannot be reused"
                )
            if existing_elfie is not None and str(existing_elfie) != str(
                configured_elfie
            ):
                raise ValueError("Node belongs to a different Elfie namespace")
            properties.setdefault("elfie_id", str(configured_elfie))
        active_submission = getattr(self, "_active_genesis_submission_id", None)
        supplied_properties = dict(node.properties)
        if (
            configured_elfie is not None
            and supplied_properties.get("elfie_id") is not None
        ):
            if str(supplied_properties["elfie_id"]) != str(configured_elfie):
                raise ValueError("Node belongs to a different Elfie namespace")
        supplied_submission = supplied_properties.get("genesis_submission_id")
        if (
            active_submission is not None
            and supplied_submission is not None
            and str(supplied_submission) != active_submission
        ):
            raise ValueError(
                "Node genesis submission does not match the active submission"
            )
        properties.update(supplied_properties)
        if configured_elfie is not None:
            # The adapter-owned namespace cannot be overwritten by caller
            # metadata, even when the caller supplies an ``elfie_id`` field.
            properties["elfie_id"] = str(configured_elfie)
        existing_submission = (
            None if existing is None else existing["genesis_submission_id"]
        )
        if active_submission is not None:
            # A Genesis package cannot smuggle an output into another
            # submission by supplying row metadata directly.  Conversely,
            # reusing a row committed by an earlier submission must not retag
            # it, otherwise that earlier package would become unreadable.
            properties["genesis_submission_id"] = (
                active_submission
                if existing_submission is None
                else str(existing_submission)
            )
        description = node.description
        if description is None and existing is not None:
            description = existing["description"]
        first_seen = (
            existing["first_seen_at"]
            if existing is not None and existing["first_seen_at"]
            else now
        )
        admission_days = MemoryScorePolicy.admission_retention(node.retention_class)
        retention_days = (
            float(existing["retention_days"])
            if existing is not None and existing["retention_days"] is not None
            else admission_days
        )
        if (
            existing is None
            and getattr(self, "_active_genesis_submission_id", None) is not None
        ):
            retention_days = MemoryScorePolicy.initial_retention("genesis")
        anchor = (
            str(existing["last_reinforced_at"])
            if existing is not None and existing["last_reinforced_at"]
            else now
        )
        next_review_at = (
            str(existing["next_review_at"])
            if existing is not None and existing["next_review_at"]
            else MemoryScorePolicy.next_review_at(
                anchor,
                retention_days,
                MemoryScorePolicy.active_freshness_threshold,
            ).isoformat(timespec="milliseconds")
        )
        effective_importance = (
            float(existing["importance"])
            if existing is not None and existing["importance"] is not None
            else node.importance
        )
        initial_importance = (
            float(existing["initial_importance"])
            if existing is not None and existing["initial_importance"] is not None
            else node.initial_importance
        )
        initial_confidence = (
            float(existing["initial_confidence"])
            if existing is not None and existing["initial_confidence"] is not None
            else node.initial_confidence
        )
        prior_weight = (
            float(existing["prior_weight"])
            if existing is not None and existing["prior_weight"] is not None
            else node.prior_weight
        )
        lifecycle_changed_at = (
            str(existing["lifecycle_changed_at"])
            if existing is not None and existing["lifecycle_changed_at"]
            else now
        )
        self.conn.execute(
            """INSERT INTO nodes (
                   node_id, node_type, canonical_label, normalized_label,
                   description, scope, status, confidence, initial_confidence, prior_weight,
                   importance, initial_importance, retention_days, properties_json,
                   first_seen_at, last_seen_at, updated_at, privacy_scope,
                   genesis_submission_id, last_reinforced_at, last_reviewed_at,
                   next_review_at, lifecycle_changed_at, policy_version
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET
                   node_type=excluded.node_type,
                   canonical_label=excluded.canonical_label,
                   normalized_label=excluded.normalized_label,
                   description=COALESCE(excluded.description, nodes.description),
                   scope=excluded.scope,
                   status=excluded.status,
                   confidence=nodes.confidence,
                   initial_confidence=nodes.initial_confidence,
                   prior_weight=nodes.prior_weight,
                   importance=nodes.importance,
                   initial_importance=nodes.initial_importance,
                   retention_days=nodes.retention_days,
                   properties_json=excluded.properties_json,
                   last_seen_at=excluded.last_seen_at,
                   updated_at=excluded.updated_at,
                   privacy_scope=excluded.privacy_scope,
                   genesis_submission_id=CASE
                       WHEN nodes.genesis_submission_id IS NOT NULL
                           THEN nodes.genesis_submission_id
                       ELSE excluded.genesis_submission_id
                   END,
                   last_reinforced_at=COALESCE(nodes.last_reinforced_at, excluded.last_reinforced_at),
                   next_review_at=nodes.next_review_at,
                   lifecycle_changed_at=CASE
                       WHEN nodes.status=excluded.status THEN nodes.lifecycle_changed_at
                       ELSE excluded.lifecycle_changed_at
                   END,
                   policy_version=excluded.policy_version""",
            (
                node.node_id,
                node.node_type,
                label,
                normalize_text(label),
                description,
                node.scope,
                node.status,
                bounded_score(node.confidence),
                bounded_score(initial_confidence),
                prior_weight,
                bounded_score(effective_importance),
                bounded_score(initial_importance),
                retention_days,
                canonical_json(properties),
                first_seen,
                now,
                now,
                str(properties.get("privacy_scope", "private")),
                properties.get("genesis_submission_id") or active_submission,
                anchor,
                None,
                next_review_at,
                lifecycle_changed_at,
                MemoryScorePolicy.version,
            ),
        )
        if existing is None:
            self._record_importance_event_locked(
                ImportanceEvent(
                    event_id=stable_id(
                        "importance-event:",
                        "node",
                        node.node_id,
                        "admission",
                        length=48,
                    ),
                    target_kind="node",
                    target_id=node.node_id,
                    direction="raise",
                    event_class="admission",
                    source_episode_id=None,
                    occurred_at=now,
                ),
                now,
            )
        else:
            target = self._importance_target_locked("node", node.node_id)
            if target is not None:
                self._ensure_importance_baseline_locked(
                    "node", node.node_id, target, now
                )
        self.conn.execute(
            """INSERT INTO nodes_fts(node_id, searchable_text) VALUES (?, ?)
               ON CONFLICT(node_id) DO UPDATE SET searchable_text=excluded.searchable_text""",
            (
                node.node_id,
                "\n".join(value for value in (label, description or "") if value),
            ),
        )

    def _insert_alias(self, alias: AliasInput, now: str) -> None:
        if alias.evidence_id is not None:
            self._require_direct_evidence(alias.evidence_id)
        self.conn.execute(
            """INSERT INTO node_aliases (
                   alias_id, node_id, alias, normalized_alias, scope,
                   evidence_id, confidence, genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(node_id, normalized_alias, scope) DO UPDATE SET
                   evidence_id=COALESCE(excluded.evidence_id, node_aliases.evidence_id),
                   confidence=MAX(node_aliases.confidence, excluded.confidence)""",
            (
                stable_id(
                    "alias:",
                    alias.node_id,
                    normalize_text(alias.alias),
                    alias.scope,
                    length=24,
                ),
                alias.node_id,
                alias.alias.strip(),
                normalize_text(alias.alias),
                alias.scope,
                alias.evidence_id,
                bounded_score(alias.confidence),
                getattr(self, "_active_genesis_submission_id", None),
                now,
            ),
        )
        self._refresh_node_text_projection(alias.node_id)
        if alias.evidence_id is not None:
            self._record_direct_node_evidence_locked(
                alias.node_id, alias.evidence_id, now
            )

    def _insert_description(self, description: DescriptionInput, now: str) -> None:
        if description.evidence_id is not None:
            self._require_direct_evidence(description.evidence_id)
        digest = content_hash(description.text)
        self.conn.execute(
            """INSERT OR IGNORE INTO node_descriptions (
                   description_id, node_id, text, language, kind,
                   content_sha256, evidence_id, confidence, genesis_submission_id,
                   created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "description:"
                + hashlib.sha256(
                    f"{description.node_id}|{description.language}|{description.kind}|{digest}".encode()
                ).hexdigest()[:24],
                description.node_id,
                description.text.strip(),
                description.language,
                description.kind,
                digest,
                description.evidence_id,
                bounded_score(description.confidence),
                getattr(self, "_active_genesis_submission_id", None),
                now,
            ),
        )
        self._refresh_node_text_projection(description.node_id)
        if description.evidence_id is not None:
            self._record_direct_node_evidence_locked(
                description.node_id, description.evidence_id, now
            )

    def _insert_mention(self, mention: MentionInput, now: str) -> None:
        # SQLite treats NULLs as distinct in a UNIQUE constraint.  Resolve the
        # nullable span explicitly so replaying the same semantic mention is
        # idempotent even when no character offsets were extracted.
        existing = self.conn.execute(
            """SELECT mention_id FROM episode_mentions
                WHERE episode_id=? AND surface_text=?
                  AND ((span_start=? ) OR (span_start IS NULL AND ? IS NULL))
                  AND ((span_end=? ) OR (span_end IS NULL AND ? IS NULL))""",
            (
                mention.episode_id,
                mention.surface_text.strip(),
                mention.span_start,
                mention.span_start,
                mention.span_end,
                mention.span_end,
            ),
        ).fetchone()
        mention_id = (
            str(existing["mention_id"])
            if existing is not None
            else stable_id(
                "mention:",
                mention.episode_id,
                normalize_text(mention.surface_text),
                mention.span_start,
                mention.span_end,
                length=32,
            )
        )
        if mention.evidence_id is not None:
            self._require_direct_evidence(mention.evidence_id)
        self.conn.execute(
            """INSERT INTO episode_mentions (
                   mention_id, episode_id, node_id, resolution_state, role,
                   surface_text, span_start, span_end, confidence, evidence_id,
                   genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(episode_id, surface_text, span_start, span_end)
               DO UPDATE SET node_id=COALESCE(excluded.node_id, episode_mentions.node_id),
                   resolution_state=excluded.resolution_state,
                   confidence=MAX(episode_mentions.confidence, excluded.confidence),
                   evidence_id=COALESCE(excluded.evidence_id, episode_mentions.evidence_id)""",
            (
                mention_id,
                mention.episode_id,
                mention.node_id,
                mention.resolution_state,
                mention.role,
                mention.surface_text.strip(),
                mention.span_start,
                mention.span_end,
                bounded_score(mention.confidence),
                mention.evidence_id,
                getattr(self, "_active_genesis_submission_id", None),
                now,
            ),
        )
        if mention.node_id is not None and mention.evidence_id is not None:
            self._record_direct_node_evidence_locked(
                mention.node_id, mention.evidence_id, now
            )

    def _insert_evidence(self, evidence: EvidenceInput, now: str) -> None:
        independence_key = evidence.independence_key or _default_independence_key(
            evidence
        )
        reliability_class = evidence.source_reliability_class
        if evidence.source_type == "seed" and reliability_class == "observed":
            reliability_class = "seed"
        # Resolve the class here so an invalid model/source proposal fails in
        # the same transaction as its Evidence row.
        MemoryScorePolicy.source_reliability_weight(reliability_class)
        if evidence.source_type == "episode":
            source_scope = ""
            source_params: list[object] = [evidence.source_id]
            if getattr(self, "elfie_id", None) is not None:
                source_scope = (
                    " AND json_extract(source_e.metadata_json, '$.elfie_id')=?"
                )
                source_params.append(str(self.elfie_id))
            source_visibility, source_visibility_params = self._genesis_visibility(
                "source_e"
            )
            source_params.extend(source_visibility_params)
            source_row = self.conn.execute(
                "SELECT source_e.content_sha256, source_e.source_version "
                "FROM episodes AS source_e WHERE source_e.episode_id=?"
                + source_scope
                + " AND "
                + source_visibility,
                source_params,
            ).fetchone()
            if source_row is None:
                raise ValueError(
                    f"Episode evidence points to an unknown source: {evidence.source_id}"
                )
            if evidence.source_sha256 is not None and evidence.source_sha256 != str(
                source_row["content_sha256"]
            ):
                raise ValueError(
                    "Episode evidence source hash does not match the source Episode"
                )
            if (
                evidence.source_version is not None
                and source_row["source_version"] is not None
                and evidence.source_version != str(source_row["source_version"])
            ):
                raise ValueError(
                    "Episode evidence source version does not match the source Episode"
                )
        existing = self.conn.execute(
            """SELECT source_type, source_id, excerpt, media_locator, modality,
                              span_start, span_end, speaker, viewpoint,
                              captured_at, extraction_run_id, source_sha256,
                              source_version, attribution, independence_key,
                              source_reliability_class, source_policy_version,
                              genesis_submission_id
                         FROM evidence WHERE evidence_id=?""",
            (evidence.evidence_id,),
        ).fetchone()
        if existing is not None and (
            str(existing["source_type"]) != evidence.source_type
            or str(existing["source_id"]) != evidence.source_id
            or existing["excerpt"] != evidence.excerpt
            or existing["media_locator"] != evidence.media_locator
            or str(existing["modality"]) != evidence.modality
            or existing["span_start"] != evidence.span_start
            or existing["span_end"] != evidence.span_end
            or existing["speaker"] != evidence.speaker
            or existing["viewpoint"] != evidence.viewpoint
            or existing["captured_at"] != evidence.captured_at
            or existing["extraction_run_id"] != evidence.extraction_run_id
            or existing["source_sha256"] != evidence.source_sha256
            or existing["source_version"] != evidence.source_version
            or existing["attribution"] != evidence.attribution
            or str(existing["independence_key"] or "") != independence_key
            or str(existing["source_reliability_class"] or "") != reliability_class
            or str(existing["source_policy_version"] or "")
            != evidence.source_policy_version
        ):
            raise ValueError(
                f"evidence ID is already bound to different source data: {evidence.evidence_id}"
            )
        active_submission = getattr(self, "_active_genesis_submission_id", None)
        if (
            active_submission is not None
            and evidence.genesis_submission_id is not None
            and evidence.genesis_submission_id != active_submission
        ):
            raise ValueError(
                "Evidence genesis submission does not match the active submission"
            )
        self.conn.execute(
            """INSERT OR IGNORE INTO evidence (
                   evidence_id, source_type, source_id, excerpt, media_locator,
                   modality, span_start, span_end, speaker, viewpoint,
                   captured_at, extraction_run_id, source_sha256, source_version,
                   attribution, independence_key, source_reliability_class,
                   source_policy_version, genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.evidence_id,
                evidence.source_type,
                evidence.source_id,
                evidence.excerpt,
                evidence.media_locator,
                evidence.modality,
                evidence.span_start,
                evidence.span_end,
                evidence.speaker,
                evidence.viewpoint,
                evidence.captured_at,
                evidence.extraction_run_id,
                evidence.source_sha256,
                evidence.source_version,
                evidence.attribution,
                independence_key,
                reliability_class,
                evidence.source_policy_version,
                active_submission or evidence.genesis_submission_id,
                now,
            ),
        )

    def _refresh_all_text_projections(self) -> None:
        """Rebuild node search text inside an existing write transaction."""
        for row in self.conn.execute("SELECT node_id FROM nodes").fetchall():
            self._refresh_node_text_projection(str(row[0]))

    def _refresh_node_text_projection(self, node_id: str) -> None:
        row = self.conn.execute(
            "SELECT canonical_label, description FROM nodes WHERE node_id=?",
            (node_id,),
        ).fetchone()
        if row is None:
            return
        values = [str(row["canonical_label"])]
        if row["description"]:
            values.append(str(row["description"]))
        values.extend(
            str(item[0])
            for item in self.conn.execute(
                "SELECT alias FROM node_aliases WHERE node_id=? ORDER BY alias_id",
                (node_id,),
            ).fetchall()
        )
        values.extend(
            str(item[0])
            for item in self.conn.execute(
                "SELECT text FROM node_descriptions WHERE node_id=? ORDER BY description_id",
                (node_id,),
            ).fetchall()
        )
        self.conn.execute(
            """INSERT INTO nodes_fts(node_id, searchable_text) VALUES (?, ?)
               ON CONFLICT(node_id) DO UPDATE SET searchable_text=excluded.searchable_text""",
            (node_id, "\n".join(value for value in values if value)),
        )

    def _insert_assertion(self, assertion: AssertionInput, now: str) -> str:
        canonical_predicate = resolve_predicate(assertion.predicate)
        if canonical_predicate != assertion.predicate:
            assertion = replace(assertion, predicate=canonical_predicate)
        if assertion.predicate_registry_version != PREDICATE_REGISTRY_VERSION:
            raise ValueError(
                "assertion predicate registry version is not supported: "
                + assertion.predicate_registry_version
            )
        configured_elfie = getattr(self, "elfie_id", None)
        if configured_elfie is not None:
            node_ids = tuple(
                dict.fromkeys(
                    node_id
                    for node_id in (assertion.subject_id, assertion.object_node_id)
                    if node_id is not None
                )
            )
            placeholders = ",".join("?" for _ in node_ids)
            rows = self.conn.execute(
                "SELECT node_id, properties_json FROM nodes WHERE node_id IN ("
                + placeholders
                + ")",
                node_ids,
            ).fetchall()
            owners = {
                str(row["node_id"]): json_object(row["properties_json"]).get("elfie_id")
                for row in rows
            }
            if any(
                owners.get(node_id) is None
                or str(owners[node_id]) != str(configured_elfie)
                for node_id in node_ids
            ):
                raise ValueError("Assertion references a different Elfie namespace")
        fingerprint = _assertion_fingerprint(assertion)
        assertion_id = assertion.assertion_id or "assertion:" + fingerprint[:24]
        existing_by_id = self.conn.execute(
            "SELECT fingerprint, initial_confidence, prior_weight, importance, "
            "initial_importance, retention_days, last_reinforced_at, next_review_at, "
            "lifecycle_changed_at FROM assertions WHERE assertion_id=?",
            (assertion_id,),
        ).fetchone()
        if (
            existing_by_id is not None
            and str(existing_by_id["fingerprint"]) != fingerprint
        ):
            raise ValueError(
                f"assertion ID is already bound to a different claim: {assertion_id}"
            )
        base = _assertion_base(assertion)
        conflict_group = (
            assertion.conflict_group
            or "conflict:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]
        )
        existing_by_fingerprint = self.conn.execute(
            "SELECT assertion_id FROM assertions WHERE fingerprint=? AND "
            + self._assertion_namespace_predicate("assertions"),
            (fingerprint, *self._assertion_namespace_params()),
        ).fetchone()
        literal = (
            None
            if assertion.object_literal is None
            else canonical_json(assertion.object_literal)
        )
        # Importance is the lifecycle/retrieval score. Evidence reinforcement
        # is applied through the single versioned score policy below.
        effective_importance = (
            float(existing_by_id["importance"])
            if existing_by_id is not None and existing_by_id["importance"] is not None
            else bounded_score(assertion.importance)
        )
        initial_importance = (
            float(existing_by_id["initial_importance"])
            if existing_by_id is not None
            and existing_by_id["initial_importance"] is not None
            else assertion.initial_importance
        )
        admission_days = MemoryScorePolicy.admission_retention(
            assertion.retention_class
        )
        retention_days = (
            float(existing_by_id["retention_days"])
            if existing_by_id is not None
            and existing_by_id["retention_days"] is not None
            else admission_days
        )
        if (
            existing_by_id is None
            and getattr(self, "_active_genesis_submission_id", None) is not None
        ):
            retention_days = MemoryScorePolicy.initial_retention("genesis")
        anchor = (
            str(existing_by_id["last_reinforced_at"])
            if existing_by_id is not None and existing_by_id["last_reinforced_at"]
            else now
        )
        next_review_at = (
            str(existing_by_id["next_review_at"])
            if existing_by_id is not None and existing_by_id["next_review_at"]
            else MemoryScorePolicy.next_review_at(
                anchor,
                retention_days,
                MemoryScorePolicy.active_freshness_threshold,
            ).isoformat(timespec="milliseconds")
        )
        initial_confidence = (
            float(existing_by_id["initial_confidence"])
            if existing_by_id is not None
            and existing_by_id["initial_confidence"] is not None
            else assertion.initial_confidence
        )
        prior_weight = (
            float(existing_by_id["prior_weight"])
            if existing_by_id is not None and existing_by_id["prior_weight"] is not None
            else assertion.prior_weight
        )
        lifecycle_changed_at = (
            str(existing_by_id["lifecycle_changed_at"])
            if existing_by_id is not None and existing_by_id["lifecycle_changed_at"]
            else now
        )
        active_submission = getattr(self, "_active_genesis_submission_id", None)
        if (
            active_submission is not None
            and assertion.genesis_submission_id is not None
            and assertion.genesis_submission_id != active_submission
        ):
            raise ValueError(
                "Assertion genesis submission does not match the active submission"
            )
        self.conn.execute(
            """INSERT INTO assertions (
                   assertion_id, subject_node_id, predicate, object_node_id,
                   object_literal_json, object_literal_type, object_unit, polarity,
                   epistemic_status, viewpoint, context, valid_from, valid_to,
                   confidence, initial_confidence, prior_weight, importance, initial_importance,
                   retention_days,
                   conflict_group, fingerprint,
                   lifecycle, supersedes_assertion_id, predicate_registry_version,
                   policy_version, genesis_submission_id, last_reinforced_at,
                   last_reviewed_at, next_review_at, lifecycle_changed_at, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(fingerprint) DO UPDATE SET
                   confidence=assertions.confidence,
                   initial_confidence=assertions.initial_confidence,
                   prior_weight=assertions.prior_weight,
                   importance=assertions.importance,
                   initial_importance=assertions.initial_importance,
                   retention_days=assertions.retention_days,
                   updated_at=excluded.updated_at,
                   predicate_registry_version=excluded.predicate_registry_version,
                   policy_version=excluded.policy_version,
                   last_reinforced_at=COALESCE(assertions.last_reinforced_at, excluded.last_reinforced_at),
                   next_review_at=assertions.next_review_at,
                   lifecycle_changed_at=CASE
                       WHEN assertions.lifecycle=excluded.lifecycle THEN assertions.lifecycle_changed_at
                       ELSE excluded.lifecycle_changed_at
                   END""",
            (
                assertion_id,
                assertion.subject_id,
                assertion.predicate,
                assertion.object_node_id,
                literal,
                assertion.object_literal_type
                or _literal_type(assertion.object_literal),
                assertion.object_unit,
                assertion.polarity,
                assertion.epistemic_status,
                assertion.viewpoint,
                assertion.context,
                assertion.valid_from,
                assertion.valid_to,
                bounded_score(assertion.confidence),
                bounded_score(initial_confidence),
                prior_weight,
                bounded_score(effective_importance),
                bounded_score(initial_importance),
                retention_days,
                conflict_group,
                fingerprint,
                assertion.supersedes_assertion_id,
                assertion.predicate_registry_version,
                MemoryScorePolicy.version,
                active_submission or assertion.genesis_submission_id,
                anchor,
                None,
                next_review_at,
                lifecycle_changed_at,
                now,
                now,
            ),
        )
        row = self.conn.execute(
            "SELECT assertion_id FROM assertions WHERE fingerprint=? AND "
            + self._assertion_namespace_predicate("assertions"),
            (fingerprint, *self._assertion_namespace_params()),
        ).fetchone()
        if row is None:
            raise RuntimeError("assertion write did not return an ID")
        stored_assertion_id = str(row["assertion_id"])
        if existing_by_fingerprint is None:
            self._record_importance_event_locked(
                ImportanceEvent(
                    event_id=stable_id(
                        "importance-event:",
                        "assertion",
                        stored_assertion_id,
                        "admission",
                        length=48,
                    ),
                    target_kind="assertion",
                    target_id=stored_assertion_id,
                    direction="raise",
                    event_class="admission",
                    source_episode_id=None,
                    occurred_at=now,
                ),
                now,
            )
        else:
            target = self._importance_target_locked("assertion", stored_assertion_id)
            if target is not None:
                self._ensure_importance_baseline_locked(
                    "assertion", stored_assertion_id, target, now
                )
        return stored_assertion_id

    def _insert_assertion_evidence(
        self, link: AssertionEvidenceInput, assertion_id: str, now: str
    ) -> None:
        existing = self.conn.execute(
            "SELECT stance FROM assertion_evidence WHERE assertion_id=? AND evidence_id=?",
            (assertion_id, link.evidence_id),
        ).fetchone()
        if existing is not None:
            # A replay of the same sourced link is a semantic no-op.  If two
            # projections disagree about its stance, retain the conservative
            # context marker but never apply a second score contribution.
            if str(existing["stance"]) != link.stance:
                self.conn.execute(
                    "UPDATE assertion_evidence SET stance='context' "
                    "WHERE assertion_id=? AND evidence_id=?",
                    (assertion_id, link.evidence_id),
                )
                self._recompute_assertion_confidence(assertion_id=assertion_id, now=now)
            return
        self.conn.execute(
            """INSERT INTO assertion_evidence (
                   assertion_id, evidence_id, stance, genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(assertion_id, evidence_id) DO UPDATE SET
                   stance=CASE
                       WHEN assertion_evidence.stance=excluded.stance
                           THEN assertion_evidence.stance
                       ELSE 'context'
                   END""",
            (
                assertion_id,
                link.evidence_id,
                link.stance,
                getattr(self, "_active_genesis_submission_id", None),
                now,
            ),
        )
        self._recompute_assertion_confidence(assertion_id=assertion_id, now=now)
        if link.stance != "context":
            evidence_row = self.conn.execute(
                "SELECT captured_at FROM evidence WHERE evidence_id=?",
                (link.evidence_id,),
            ).fetchone()
            event_time = (
                str(evidence_row["captured_at"])
                if evidence_row is not None and evidence_row["captured_at"]
                else now
            )
            self._reinforce_target_locked(
                target_kind="assertion",
                target_id=assertion_id,
                occurred_at=event_time,
                source_ref=link.evidence_id,
                outcome_kind="independent_evidence",
                now=now,
            )

    def _recompute_assertion_confidence(
        self,
        *,
        assertion_id: str,
        now: str,
    ) -> None:
        row = self.conn.execute(
            "SELECT initial_confidence, prior_weight "
            "FROM assertions WHERE assertion_id=?",
            (assertion_id,),
        ).fetchone()
        if row is None:
            return
        contributions = self._evidence_contributions_for_assertion(assertion_id)
        confidence = MemoryScorePolicy.confidence_from_evidence(
            initial_confidence=float(row["initial_confidence"] or 0.5),
            prior_weight=float(row["prior_weight"] or 1.0),
            contributions=contributions,
        )
        self.conn.execute(
            """UPDATE assertions SET confidence=?, policy_version=?, updated_at=?
               WHERE assertion_id=?""",
            (
                confidence,
                MemoryScorePolicy.version,
                now,
                assertion_id,
            ),
        )

    def _evidence_contributions_for_assertion(
        self, assertion_id: str
    ) -> tuple[EvidenceContribution, ...]:
        rows = self.conn.execute(
            """SELECT e.evidence_id, e.independence_key, e.source_reliability_class,
                      e.genesis_submission_id, ae.stance
                 FROM assertion_evidence AS ae
                 JOIN evidence AS e ON e.evidence_id=ae.evidence_id
                WHERE ae.assertion_id=?
                ORDER BY e.evidence_id""",
            (assertion_id,),
        ).fetchall()
        return tuple(
            EvidenceContribution(
                evidence_id=str(row["evidence_id"]),
                independence_key=str(row["independence_key"] or row["evidence_id"]),
                stance=str(row["stance"]),  # type: ignore[arg-type]
                weight=MemoryScorePolicy.source_reliability_weight(
                    str(row["source_reliability_class"] or "observed")
                ),
            )
            for row in rows
            # The Genesis source is the immutable admission prior.  Counting
            # it again as ordinary support would double-count the same fact;
            # later runtime Evidence (without a Genesis submission marker)
            # remains eligible to update C.
            if row["genesis_submission_id"] is None
        )

    def _recompute_node_confidence(self, node_id: str, now: str) -> None:
        row = self.conn.execute(
            "SELECT initial_confidence, prior_weight FROM nodes WHERE node_id=?",
            (node_id,),
        ).fetchone()
        if row is None:
            return
        # Node confidence is grounded only by evidence attached to the Node's
        # own identity observations.  Relation evidence belongs to its
        # Assertion and must never be propagated to either endpoint.
        contributions_rows = self.conn.execute(
            """SELECT e.evidence_id, e.independence_key,
                      e.source_reliability_class, e.genesis_submission_id
                 FROM node_aliases AS na
                 JOIN evidence AS e ON e.evidence_id=na.evidence_id
                WHERE na.node_id=?
                UNION ALL
               SELECT e.evidence_id, e.independence_key,
                      e.source_reliability_class, e.genesis_submission_id
                 FROM node_descriptions AS nd
                 JOIN evidence AS e ON e.evidence_id=nd.evidence_id
                WHERE nd.node_id=?
                UNION ALL
               SELECT e.evidence_id, e.independence_key,
                      e.source_reliability_class, e.genesis_submission_id
                 FROM episode_mentions AS em
                 JOIN evidence AS e ON e.evidence_id=em.evidence_id
                WHERE em.node_id=? AND em.resolution_state='resolved'
                ORDER BY 1""",
            (node_id, node_id, node_id),
        ).fetchall()
        contributions = tuple(
            EvidenceContribution(
                evidence_id=str(item["evidence_id"]),
                independence_key=str(item["independence_key"] or item["evidence_id"]),
                stance="supports",
                weight=MemoryScorePolicy.source_reliability_weight(
                    str(item["source_reliability_class"] or "observed")
                ),
            )
            for item in contributions_rows
            if item["genesis_submission_id"] is None
        )
        confidence = MemoryScorePolicy.confidence_from_evidence(
            initial_confidence=float(row["initial_confidence"] or 0.5),
            prior_weight=float(row["prior_weight"] or 1.0),
            contributions=contributions,
        )
        self.conn.execute(
            "UPDATE nodes SET confidence=?, policy_version=?, updated_at=? WHERE node_id=?",
            (confidence, MemoryScorePolicy.version, now, node_id),
        )

    def _require_direct_evidence(self, evidence_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT evidence_id, source_type, source_id FROM evidence WHERE evidence_id=?",
            (evidence_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown direct Node evidence: {evidence_id}")
        if getattr(self, "elfie_id", None) is not None:
            if str(row["source_type"]) == "episode":
                owner = self.conn.execute(
                    "SELECT json_extract(metadata_json, '$.elfie_id') AS elfie_id "
                    "FROM episodes WHERE episode_id=?",
                    (row["source_id"],),
                ).fetchone()
                if owner is None or str(owner["elfie_id"]) != str(self.elfie_id):
                    raise ValueError("direct Node evidence belongs to another Elfie")
        return row

    def _record_direct_node_evidence_locked(
        self, node_id: str, evidence_id: str, now: str
    ) -> None:
        """Recompute and reinforce exactly the Node named by an observation."""
        self._recompute_node_confidence(node_id, now)
        evidence_row = self.conn.execute(
            "SELECT captured_at FROM evidence WHERE evidence_id=?",
            (evidence_id,),
        ).fetchone()
        event_time = (
            str(evidence_row["captured_at"])
            if evidence_row is not None and evidence_row["captured_at"]
            else now
        )
        self._reinforce_target_locked(
            target_kind="node",
            target_id=node_id,
            occurred_at=event_time,
            source_ref=evidence_id,
            outcome_kind="independent_evidence",
            now=now,
        )

    def _reinforce_target_locked(
        self,
        *,
        target_kind: str,
        target_id: str,
        occurred_at: str,
        source_ref: str,
        outcome_kind: str,
        now: str,
        recall_revision: int | None = None,
        receipt_id: str | None = None,
    ) -> bool:
        """Apply one idempotent qualified retention receipt in the current UoW."""
        if not source_ref.strip():
            raise ValueError("retention source_ref must not be blank")
        MemoryScorePolicy.validate_event_time(now=now, occurred_at=occurred_at)
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        receipt_id = receipt_id or stable_id(
            "retention:", target_kind, target_id, source_ref, outcome_kind, length=48
        )
        existing = self.conn.execute(
            """SELECT target_kind, target_id, occurred_at, outcome_kind,
                              source_ref, recall_revision, state, policy_version
                 FROM memory_retention_receipts
                WHERE elfie_id=? AND receipt_id=?""",
            (elfie_id, receipt_id),
        ).fetchone()
        if existing is not None:
            # ``state`` is deliberately ignored in the identity check;
            # replay can legitimately reclassify an event after a late
            # receipt changes the event-time fold.
            if (
                str(existing["target_kind"]) != target_kind
                or str(existing["target_id"]) != target_id
                or str(existing["occurred_at"]) != occurred_at
                or str(existing["outcome_kind"]) != outcome_kind
                or str(existing["source_ref"]) != source_ref
                or existing["recall_revision"] != recall_revision
            ):
                raise ValueError(
                    "retention receipt identity was reused with different content"
                )
            return str(existing["state"]) == "accepted"
        row = self._retention_target_locked(target_kind, target_id)
        if row is None:
            return False
        if not _retention_target_is_active(target_kind, row):
            self.conn.execute(
                """INSERT INTO memory_retention_receipts(
                       receipt_id, elfie_id, target_kind, target_id, occurred_at,
                       outcome_kind, source_ref, recall_revision, state,
                       policy_version, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ignored', ?, ?)""",
                (
                    receipt_id,
                    elfie_id,
                    target_kind,
                    target_id,
                    occurred_at,
                    outcome_kind,
                    source_ref,
                    recall_revision,
                    MemoryScorePolicy.version,
                    now,
                ),
            )
            return False
        # Retention receipts are folded from one immutable baseline in event
        # time.  This prevents a later-delivered older event from producing a
        # different D/anchor than the same events delivered chronologically.
        self._ensure_retention_baseline_locked(target_kind, target_id, row, now)
        folded = self.conn.execute(
            """SELECT folded_through FROM memory_score_checkpoints
                  WHERE elfie_id=? AND target_kind=? AND target_id=?
                    AND score_kind='retention'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        if folded is not None and folded["folded_through"] is not None:
            if _parse_utc_timestamp(occurred_at) <= _parse_utc_timestamp(
                str(folded["folded_through"])
            ):
                self.conn.execute(
                    """INSERT OR IGNORE INTO memory_retention_receipts(
                           receipt_id, elfie_id, target_kind, target_id,
                           occurred_at, outcome_kind, source_ref, recall_revision,
                           state, policy_version, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reconciled', ?, ?)""",
                    (
                        receipt_id,
                        elfie_id,
                        target_kind,
                        target_id,
                        occurred_at,
                        outcome_kind,
                        source_ref,
                        recall_revision,
                        MemoryScorePolicy.version,
                        now,
                    ),
                )
                self._record_score_reconciliation_locked(
                    target_kind=target_kind,
                    target_id=target_id,
                    score_kind="retention",
                    reason="late_event_before_folded_watermark",
                    payload={
                        "receipt_id": receipt_id,
                        "occurred_at": occurred_at,
                        "folded_through": str(folded["folded_through"]),
                    },
                    now=now,
                )
                return False
        self.conn.execute(
            """INSERT INTO memory_retention_receipts(
                   receipt_id, elfie_id, target_kind, target_id, occurred_at,
                   outcome_kind, source_ref, recall_revision, state, policy_version, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt_id,
                elfie_id,
                target_kind,
                target_id,
                occurred_at,
                outcome_kind,
                source_ref,
                recall_revision,
                "accepted",
                MemoryScorePolicy.version,
                now,
            ),
        )
        return self._replay_retention_target_locked(
            target_kind, target_id, receipt_id, now
        )

    def _record_score_reconciliation_locked(
        self,
        *,
        target_kind: str,
        target_id: str,
        score_kind: str,
        reason: str,
        payload: dict[str, object],
        now: str,
    ) -> None:
        reconciliation_id = stable_id(
            "score-reconciliation:",
            score_kind,
            target_kind,
            target_id,
            reason,
            payload,
            length=48,
        )
        self.conn.execute(
            """INSERT OR IGNORE INTO memory_score_reconciliation(
                   reconciliation_id, elfie_id, target_kind, target_id,
                   score_kind, reason, payload_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reconciliation_id,
                str(getattr(self, "elfie_id", "") or ""),
                target_kind,
                target_id,
                score_kind,
                reason,
                canonical_json(payload),
                now,
            ),
        )

    def _importance_target_locked(
        self, target_kind: str, target_id: str
    ) -> sqlite3.Row | None:
        table, key_column = _importance_target_table(target_kind)
        if target_kind == "episode":
            namespace = ""
            params: list[object] = [target_id]
            if getattr(self, "elfie_id", None) is not None:
                namespace = " AND json_extract(metadata_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            return self.conn.execute(
                f"SELECT initial_importance, importance FROM {table} WHERE {key_column}=?{namespace}",
                params,
            ).fetchone()
        if target_kind == "node":
            namespace = ""
            params = [target_id]
            if getattr(self, "elfie_id", None) is not None:
                namespace = " AND json_extract(properties_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            return self.conn.execute(
                f"SELECT initial_importance, importance FROM {table} WHERE {key_column}=?{namespace}",
                params,
            ).fetchone()
        if target_kind == "assertion":
            namespace = ""
            params = [target_id]
            if getattr(self, "elfie_id", None) is not None:
                namespace = (
                    " AND EXISTS (SELECT 1 FROM nodes AS n "
                    "WHERE n.node_id=assertions.subject_node_id "
                    "AND json_extract(n.properties_json, '$.elfie_id')=?)"
                )
                params.append(str(self.elfie_id))
            return self.conn.execute(
                f"SELECT initial_importance, importance FROM {table} WHERE {key_column}=?{namespace}",
                params,
            ).fetchone()
        raise ValueError(f"unsupported importance target kind: {target_kind}")

    def _ensure_importance_baseline_locked(
        self,
        target_kind: str,
        target_id: str,
        row: sqlite3.Row,
        now: str,
    ) -> None:
        """Create the replay baseline for one target exactly once."""
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        existing = self.conn.execute(
            """SELECT 1 FROM memory_score_checkpoints
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='importance'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        if existing is not None:
            return
        initial = float(row["initial_importance"] or row["importance"] or 0.5)
        self.conn.execute(
            """INSERT INTO memory_score_checkpoints(
                   elfie_id, target_kind, target_id, score_kind, folded_through,
                   state_json, event_count, policy_version, updated_at
               ) VALUES (?, ?, ?, 'importance', NULL, ?, 0, ?, ?)""",
            (
                elfie_id,
                target_kind,
                target_id,
                canonical_json(
                    {
                        "base_importance": initial,
                        "current_importance": initial,
                        "folded_event_count": 0,
                        "folded_event_ids": [],
                        "folded_event_hash": _empty_fold_hash("importance"),
                        "last_event_time": None,
                    }
                ),
                MemoryScorePolicy.version,
                now,
            ),
        )

    def _replay_importance_target_locked(
        self, target_kind: str, target_id: str, now: str
    ) -> None:
        """Rebuild current ``importance`` from checkpoint baseline + suffix."""
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        checkpoint = self.conn.execute(
            """SELECT folded_through, state_json
                 FROM memory_score_checkpoints
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='importance'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        target = self._importance_target_locked(target_kind, target_id)
        if checkpoint is None or target is None:
            return
        state = json_object(checkpoint["state_json"])
        base = float(state.get("base_importance", target["initial_importance"] or 0.5))
        params: list[object] = [elfie_id, target_kind, target_id]
        suffix_clause = ""
        if checkpoint["folded_through"] is not None:
            suffix_clause = " AND occurred_at>?"
            params.append(str(checkpoint["folded_through"]))
        rows = self.conn.execute(
            """SELECT event_id, target_kind, target_id, direction,
                              event_class, occurred_at, source_episode_id
                 FROM memory_importance_events
                WHERE elfie_id=? AND target_kind=? AND target_id=?"""
            + suffix_clause
            + " ORDER BY occurred_at, event_id",
            params,
        ).fetchall()
        value = MemoryScorePolicy.fold_importance(
            initial=base,
            events=_importance_events_from_rows(rows),
            target_kind=target_kind,
            target_id=target_id,
        )
        self._update_importance_target_locked(
            target_kind=target_kind,
            target_id=target_id,
            importance=value,
            now=now,
        )
        folded_count = int(state.get("folded_event_count", 0) or 0)
        state.update(
            {
                "current_importance": value,
                "suffix_event_count": len(rows),
            }
        )
        self.conn.execute(
            """UPDATE memory_score_checkpoints
                  SET state_json=?, event_count=?, policy_version=?, updated_at=?
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='importance'""",
            (
                canonical_json(state),
                folded_count,
                MemoryScorePolicy.version,
                now,
                elfie_id,
                target_kind,
                target_id,
            ),
        )

    def _update_importance_target_locked(
        self,
        *,
        target_kind: str,
        target_id: str,
        importance: float,
        now: str,
    ) -> None:
        """Materialize ``I`` without touching retention, confidence or state."""
        table, key_column = _importance_target_table(target_kind)
        namespace_clause = ""
        params: list[object] = [
            bounded_score(importance),
            MemoryScorePolicy.version,
            now,
            target_id,
        ]
        if getattr(self, "elfie_id", None) is not None:
            if target_kind == "episode":
                namespace_clause = " AND json_extract(metadata_json, '$.elfie_id')=?"
            elif target_kind == "node":
                namespace_clause = " AND json_extract(properties_json, '$.elfie_id')=?"
            else:
                namespace_clause = (
                    " AND EXISTS (SELECT 1 FROM nodes AS n "
                    "WHERE n.node_id=assertions.subject_node_id "
                    "AND json_extract(n.properties_json, '$.elfie_id')=?)"
                )
            params.append(str(self.elfie_id))
        self.conn.execute(
            f"UPDATE {table} SET importance=?, policy_version=?, updated_at=? "
            f"WHERE {key_column}=?{namespace_clause}",
            params,
        )

    def _validate_event_source_locked(self, source_episode_id: str | None) -> None:
        if source_episode_id is None:
            return
        params: list[object] = [source_episode_id]
        clause = ""
        if getattr(self, "elfie_id", None) is not None:
            clause = " AND json_extract(metadata_json, '$.elfie_id')=?"
            params.append(str(self.elfie_id))
        if (
            self.conn.execute(
                "SELECT 1 FROM episodes WHERE episode_id=?" + clause,
                params,
            ).fetchone()
            is None
        ):
            raise ValueError("importance event source Episode is not visible")

    def _retention_target_locked(
        self, target_kind: str, target_id: str
    ) -> sqlite3.Row | None:
        if target_kind == "episode":
            table, key_column, namespace, state_columns = (
                "episodes",
                "episode_id",
                "json_extract(metadata_json, '$.elfie_id')=?",
                "lifecycle, NULL AS status",
            )
        elif target_kind == "node":
            table, key_column, namespace, state_columns = (
                "nodes",
                "node_id",
                "json_extract(properties_json, '$.elfie_id')=?",
                "NULL AS lifecycle, status",
            )
        elif target_kind == "assertion":
            table, key_column, namespace, state_columns = (
                "assertions",
                "assertion_id",
                "EXISTS (SELECT 1 FROM nodes AS n WHERE n.node_id=assertions.subject_node_id AND json_extract(n.properties_json, '$.elfie_id')=?)",
                "lifecycle, NULL AS status",
            )
        else:
            raise ValueError(f"unsupported retention target kind: {target_kind}")
        params: list[object] = [target_id]
        scope = ""
        if getattr(self, "elfie_id", None) is not None:
            scope = " AND " + namespace
            params.append(str(self.elfie_id))
        row = self.conn.execute(
            f"SELECT retention_days, last_reinforced_at, {state_columns}, "
            f"updated_at FROM {table} WHERE {key_column}=?{scope}",
            params,
        ).fetchone()
        return row

    def _update_retention_target_locked(
        self,
        *,
        target_kind: str,
        target_id: str,
        retention_days: float,
        anchor: str,
        next_review: str,
        now: str,
    ) -> None:
        """Materialize a replayed D/anchor without touching I or C."""
        table, key_column = _retention_target_table(target_kind)
        namespace_clause = ""
        params: list[object] = [
            retention_days,
            anchor,
            next_review,
            MemoryScorePolicy.version,
            now,
            target_id,
        ]
        if getattr(self, "elfie_id", None) is not None:
            if target_kind == "episode":
                namespace_clause = " AND json_extract(metadata_json, '$.elfie_id')=?"
            elif target_kind == "node":
                namespace_clause = " AND json_extract(properties_json, '$.elfie_id')=?"
            elif target_kind == "assertion":
                namespace_clause = (
                    " AND EXISTS (SELECT 1 FROM nodes AS n "
                    "WHERE n.node_id=assertions.subject_node_id "
                    "AND json_extract(n.properties_json, '$.elfie_id')=?)"
                )
            else:
                raise ValueError(f"unsupported retention target kind: {target_kind}")
            params.append(str(self.elfie_id))
        self.conn.execute(
            f"UPDATE {table} SET retention_days=?, last_reinforced_at=?, "
            f"next_review_at=?, policy_version=?, updated_at=? "
            f"WHERE {key_column}=?{namespace_clause}",
            params,
        )

    def _ensure_retention_baseline_locked(
        self, target_kind: str, target_id: str, row: sqlite3.Row, now: str
    ) -> None:
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        existing = self.conn.execute(
            """SELECT 1 FROM memory_score_checkpoints
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='retention'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        if existing is not None:
            return
        baseline = {
            "base_retention_days": float(row["retention_days"] or 7.0),
            "base_anchor": str(row["last_reinforced_at"] or row["updated_at"] or now),
            "current_retention_days": float(row["retention_days"] or 7.0),
            "current_anchor": str(
                row["last_reinforced_at"] or row["updated_at"] or now
            ),
            "folded_event_count": 0,
            "folded_event_hash": _empty_fold_hash("retention"),
            "last_event_time": None,
        }
        self.conn.execute(
            """INSERT INTO memory_score_checkpoints(
                   elfie_id, target_kind, target_id, score_kind, folded_through,
                   state_json, event_count, policy_version, updated_at
               ) VALUES (?, ?, ?, 'retention', NULL, ?, 0, ?, ?)""",
            (
                elfie_id,
                target_kind,
                target_id,
                canonical_json(baseline),
                MemoryScorePolicy.version,
                now,
            ),
        )

    def _replay_retention_target_locked(
        self, target_kind: str, target_id: str, receipt_id: str, now: str
    ) -> bool:
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        checkpoint = self.conn.execute(
            """SELECT folded_through, state_json FROM memory_score_checkpoints
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND score_kind='retention'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        if checkpoint is None:
            raise RuntimeError("retention baseline checkpoint is missing")
        baseline = json_object(checkpoint["state_json"])
        folded_through = checkpoint["folded_through"]
        if folded_through:
            # Once a safe prefix has been folded, the checkpoint's current
            # state is the replay baseline; the remaining receipt suffix is
            # still replayed in event-time order.
            days = float(baseline.get("current_retention_days", 7.0))
            anchor = str(baseline.get("current_anchor") or now)
        else:
            days = float(baseline.get("base_retention_days", 7.0))
            anchor = str(baseline.get("base_anchor") or now)
        rows = self.conn.execute(
            """SELECT receipt_id, occurred_at, state FROM memory_retention_receipts
                WHERE elfie_id=? AND target_kind=? AND target_id=?
                  AND state='accepted'
                ORDER BY occurred_at, receipt_id""",
            (elfie_id, target_kind, target_id),
        ).fetchall()
        accepted_current = False
        for item in rows:
            target = self._retention_target_locked(target_kind, target_id)
            if target is None:
                continue
            lifecycle = target["lifecycle"] if "lifecycle" in target.keys() else None
            status = target["status"] if "status" in target.keys() else None
            eligible = (
                (target_kind == "episode" and lifecycle == "active")
                or (target_kind == "assertion" and lifecycle == "active")
                or (
                    target_kind == "node"
                    and status in {"active", "candidate", "unresolved"}
                )
            )
            update = (
                MemoryScorePolicy.reinforce(
                    retention_days=days,
                    last_reinforced_at=anchor,
                    occurred_at=str(item["occurred_at"]),
                )
                if eligible
                else None
            )
            if update is None:
                self.conn.execute(
                    "UPDATE memory_retention_receipts SET state='ignored', policy_version=? WHERE elfie_id=? AND receipt_id=?",
                    (MemoryScorePolicy.version, elfie_id, item["receipt_id"]),
                )
                continue
            days = update.retention_days
            anchor = update.last_reinforced_at.isoformat(timespec="milliseconds")
            self.conn.execute(
                "UPDATE memory_retention_receipts SET state='accepted', policy_version=? WHERE elfie_id=? AND receipt_id=?",
                (MemoryScorePolicy.version, elfie_id, item["receipt_id"]),
            )
            if str(item["receipt_id"]) == str(receipt_id):
                accepted_current = True
        next_review = MemoryScorePolicy.next_review_at(
            anchor, days, MemoryScorePolicy.active_freshness_threshold
        ).isoformat(timespec="milliseconds")
        self._update_retention_target_locked(
            target_kind=target_kind,
            target_id=target_id,
            retention_days=days,
            anchor=anchor,
            next_review=next_review,
            now=now,
        )
        checkpoint_row = self.conn.execute(
            """SELECT folded_through FROM memory_score_checkpoints
                  WHERE elfie_id=? AND target_kind=? AND target_id=?
                    AND score_kind='retention'""",
            (elfie_id, target_kind, target_id),
        ).fetchone()
        existing_folded_through = (
            None if checkpoint_row is None else checkpoint_row["folded_through"]
        )
        folded_event_count = int(baseline.get("folded_event_count", 0) or 0)
        self.conn.execute(
            """UPDATE memory_score_checkpoints
                  SET folded_through=?, state_json=?, event_count=?, policy_version=?, updated_at=?
                WHERE elfie_id=? AND target_kind=? AND target_id=? AND score_kind='retention'""",
            (
                existing_folded_through,
                canonical_json(
                    {
                        "base_retention_days": float(
                            baseline.get("base_retention_days", 7.0)
                        ),
                        "base_anchor": str(baseline.get("base_anchor") or now),
                        "current_retention_days": days,
                        "current_anchor": anchor,
                        "folded_event_count": folded_event_count,
                        "suffix_event_count": len(rows),
                        "folded_event_hash": str(
                            baseline.get("folded_event_hash")
                            or _empty_fold_hash("retention")
                        ),
                        "last_event_time": baseline.get("last_event_time"),
                    }
                ),
                folded_event_count,
                MemoryScorePolicy.version,
                now,
                elfie_id,
                target_kind,
                target_id,
            ),
        )
        return accepted_current

    def _assertion_exists(self, assertion_id: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM assertions WHERE assertion_id=? AND "
                + self._assertion_namespace_predicate("assertions"),
                (assertion_id, *self._assertion_namespace_params()),
            ).fetchone()
            is not None
        )

    def _assertion_namespace_predicate(self, alias: str) -> str:
        if getattr(self, "elfie_id", None) is None:
            return "1=1"
        if not alias.replace("_", "").isalnum():
            raise ValueError("invalid SQL alias")
        return (
            "EXISTS (SELECT 1 FROM nodes AS assertion_node "
            f"WHERE assertion_node.node_id={alias}.subject_node_id "
            "AND json_extract(assertion_node.properties_json, '$.elfie_id')=?)"
        )

    def _assertion_namespace_params(self) -> tuple[object, ...]:
        if getattr(self, "elfie_id", None) is None:
            return ()
        return (str(self.elfie_id),)

    def _record_projection_diagnostic(
        self, projection: ConsolidationProjection, *, reason: str
    ) -> None:
        """Persist a bounded rejection record outside the failed fact UoW."""
        diagnostic_id = stable_id(
            "diagnostic:",
            projection.episode_id,
            projection.source_sha256,
            reason,
            tuple(assertion.predicate for assertion in projection.assertions),
            length=32,
        )
        owns = self._begin_write_transaction()
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO projection_diagnostics(
                       diagnostic_id, elfie_id, episode_id, predicate, reason,
                       payload_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    diagnostic_id,
                    str(getattr(self, "elfie_id", "") or ""),
                    projection.episode_id,
                    ",".join(
                        assertion.predicate for assertion in projection.assertions
                    )[:512],
                    reason,
                    canonical_json({"assertion_count": len(projection.assertions)}),
                    utc_now(),
                ),
            )
            self._commit_write_transaction(owns)
        except Exception:
            self._rollback_write_transaction(owns)

    def _latest_active_claim(
        self,
        *,
        subject_id: str,
        predicate: str,
        object_node_id: str | None,
        object_literal: object | None,
        object_literal_type: str | None,
    ) -> str | None:
        """Find a prior value for an explicit correction, never a conflict."""
        rows = self.conn.execute(
            """SELECT assertion_id, object_node_id, object_literal_json,
                              object_literal_type
                 FROM assertions
                WHERE subject_node_id=? AND predicate=? AND lifecycle='active'
                ORDER BY updated_at DESC, assertion_id DESC""",
            (subject_id, predicate),
        ).fetchall()
        desired_literal = (
            None if object_literal is None else canonical_json(object_literal)
        )
        desired_literal_type = object_literal_type or _literal_type(object_literal)
        for row in rows:
            if (
                row["object_node_id"] == object_node_id
                and row["object_literal_json"] == desired_literal
                and (
                    object_literal is None
                    or row["object_literal_type"] == desired_literal_type
                )
            ):
                continue
            return str(row["assertion_id"])
        return None


def _assertion_base(assertion: AssertionInput) -> str:
    object_value = (
        f"node:{assertion.object_node_id}"
        if assertion.object_node_id is not None
        else "|".join(
            (
                "literal",
                assertion.object_literal_type
                or _literal_type(assertion.object_literal)
                or "json",
                canonical_json(assertion.object_literal),
            )
        )
    )
    return "|".join((assertion.subject_id, assertion.predicate, object_value))


def _assertion_fingerprint(assertion: AssertionInput) -> str:
    payload = {
        "base": _assertion_base(assertion),
        "object_unit": assertion.object_unit,
        "polarity": assertion.polarity,
        "epistemic_status": assertion.epistemic_status,
        "viewpoint": assertion.viewpoint,
        "context": assertion.context,
        "valid_from": assertion.valid_from,
        "valid_to": assertion.valid_to,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _row_as_assertion_input(
    row: sqlite3.Row,
    subject_id: str,
    object_node_id: str | None,
) -> AssertionInput:
    literal = None
    if row["object_literal_json"] is not None:
        literal = json.loads(str(row["object_literal_json"]))
    # Evidence is copied separately during a merge; this object only exists to
    # recompute the qualified assertion fingerprint after changing endpoints.
    return AssertionInput(
        subject_id=str(subject_id),
        predicate=str(row["predicate"]),
        object_node_id=object_node_id,
        object_literal=literal,
        object_unit=row["object_unit"],
        polarity=str(row["polarity"]),  # type: ignore[arg-type]
        epistemic_status=str(row["epistemic_status"]),  # type: ignore[arg-type]
        viewpoint=row["viewpoint"],
        context=row["context"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        confidence=bounded_score(row["confidence"]),
        initial_confidence=bounded_score(row["initial_confidence"]),
        prior_weight=float(row["prior_weight"] or 1.0),
        conflict_group=row["conflict_group"],
        supersedes_assertion_id=row["supersedes_assertion_id"],
        importance=bounded_score(row["importance"]),
        # Merges retain the original admission baseline so event replay stays
        # independent of the order in which endpoint rows were rewritten.
        initial_importance=bounded_score(row["initial_importance"]),
        retention_days=float(row["retention_days"] or 7.0),
        retention_class=_retention_class(float(row["retention_days"] or 7.0)),
        object_literal_type=row["object_literal_type"],
        predicate_registry_version=str(
            row["predicate_registry_version"] or "memory.predicates.v1"
        ),
        policy_version=str(row["policy_version"] or MemoryScorePolicy.version),
        genesis_submission_id=row["genesis_submission_id"],
    )


def _row_to_assertion(row: sqlite3.Row, *, now: str | None = None) -> RecallAssertion:
    literal = None
    if row["object_literal_json"] is not None:
        literal = json.loads(row["object_literal_json"])
    qualifiers = {
        key: row[key]
        for key in (
            "object_unit",
            "object_literal_type",
            "viewpoint",
            "context",
            "valid_from",
            "valid_to",
            "polarity",
            "epistemic_status",
            "conflict_group",
            "supersedes_assertion_id",
        )
        if row[key] is not None
    }
    evidence_ids = tuple(
        value for value in str(row["evidence_ids_csv"] or "").split(",") if value
    )
    retention_days = float(row["retention_days"] or 7.0)
    current_now = now or utc_now()
    anchor = row["last_reinforced_at"] or row["updated_at"] or current_now
    freshness = MemoryScorePolicy.freshness(current_now, str(anchor), retention_days)
    status = str(row["lifecycle"])
    quality_confidence = float(row["confidence"]) if status == "active" else None
    score = MemoryScorePolicy.recall_score(
        relevance=1.0,
        freshness=freshness,
        importance=float(row["importance"]),
        confidence=quality_confidence,
    )
    return RecallAssertion(
        assertion_id=str(row["assertion_id"]),
        subject_id=str(row["subject_node_id"]),
        predicate=str(row["predicate"]),
        object_node_id=(
            None if row["object_node_id"] is None else str(row["object_node_id"])
        ),
        object_literal=literal,
        qualifiers=qualifiers,
        status=status,
        evidence_ids=evidence_ids,
        relevance=score.rank,
        importance=float(row["importance"]),
        confidence=float(row["confidence"]),
        freshness=freshness,
        retention_days=retention_days,
    )


def _row_to_recall_node(
    row: sqlite3.Row, *, relevance_key: str = "confidence", now: str | None = None
) -> RecallNode:
    """Decode one bounded graph row without leaking the SQLite row itself."""
    properties = json_object(row["properties_json"])
    retention_days = float(row["retention_days"] or 7.0)
    current_now = now or utc_now()
    anchor = row["last_reinforced_at"] or row["updated_at"] or current_now
    freshness = MemoryScorePolicy.freshness(current_now, str(anchor), retention_days)
    base_relevance = min(1.0, max(0.0, float(row[relevance_key])))
    score = MemoryScorePolicy.recall_score(
        relevance=base_relevance,
        freshness=freshness,
        importance=float(row["importance"]),
        confidence=float(row["confidence"]),
    )
    return RecallNode(
        node_id=str(row["node_id"]),
        node_type=str(row["node_type"]),
        label=str(row["canonical_label"]),
        description=row["description"],
        relevance=score.rank,
        importance=float(row["importance"]),
        confidence=float(row["confidence"]),
        freshness=freshness,
        retention_days=retention_days,
        properties=properties,
    )


def _literal_type(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "json"


def _default_independence_key(evidence: EvidenceInput) -> str:
    """Group one source locator into one independent confidence signal."""
    return "|".join(
        (
            evidence.source_type,
            evidence.source_id,
            evidence.source_version or "",
            evidence.modality,
            "" if evidence.span_start is None else str(evidence.span_start),
            "" if evidence.span_end is None else str(evidence.span_end),
            evidence.media_locator or "",
        )
    )


def _episode_evidence_id(conn: sqlite3.Connection, episode_id: str) -> str | None:
    """Return the stable source observation for one projected Episode.

    Consolidation creates the Episode evidence before mentions are written;
    using the persisted source key lets ordinary mention projections ground a
    Node without making relation/assertion evidence an implicit endpoint
    observation.
    """
    row = conn.execute(
        """SELECT evidence_id FROM evidence
            WHERE source_type='episode' AND source_id=?
            ORDER BY evidence_id LIMIT 1""",
        (episode_id,),
    ).fetchone()
    return None if row is None else str(row["evidence_id"])


def _retention_class(days: float) -> RetentionClass:
    if days >= MemoryScorePolicy.initial_retention("genesis"):
        return "genesis"
    if days >= MemoryScorePolicy.initial_retention("salient"):
        return "salient"
    if days <= MemoryScorePolicy.initial_retention("transient"):
        return "transient"
    return "ordinary"


def _importance_target_table(target_kind: str) -> tuple[str, str]:
    tables = {
        "episode": ("episodes", "episode_id"),
        "node": ("nodes", "node_id"),
        "assertion": ("assertions", "assertion_id"),
    }
    try:
        return tables[target_kind]
    except KeyError as exc:
        raise ValueError(f"unsupported importance target kind: {target_kind}") from exc


def _importance_events_from_rows(
    rows: Iterable[sqlite3.Row],
) -> tuple[ImportanceEvent, ...]:
    """Decode adapter rows into the policy's immutable event type."""
    return tuple(
        ImportanceEvent(
            event_id=str(row["event_id"]),
            target_kind=str(row["target_kind"]),
            target_id=str(row["target_id"]),
            direction=str(row["direction"]),  # type: ignore[arg-type]
            event_class=str(row["event_class"]),
            occurred_at=str(row["occurred_at"]),
            source_episode_id=row["source_episode_id"],
        )
        for row in rows
    )


def _empty_fold_hash(score_kind: str) -> str:
    """Return the deterministic hash anchor for one score-control stream."""
    return hashlib.sha256(
        f"{MemoryScorePolicy.version}:{score_kind}:empty".encode()
    ).hexdigest()


def _extend_fold_hash(previous: str, tokens: Iterable[dict[str, object]]) -> str:
    """Extend a checkpoint hash chain without retaining every folded row."""
    digest = previous
    for token in tokens:
        digest = hashlib.sha256(
            (digest + "\x1f" + canonical_json(token)).encode("utf-8")
        ).hexdigest()
    return digest


def _importance_fold_tokens(
    rows: Iterable[sqlite3.Row],
) -> tuple[dict[str, object], ...]:
    """Canonical immutable fields used to audit an importance fold."""
    return tuple(
        {
            "event_id": str(row["event_id"]),
            "target_kind": str(row["target_kind"]),
            "target_id": str(row["target_id"]),
            "direction": str(row["direction"]),
            "event_class": str(row["event_class"]),
            "source_episode_id": row["source_episode_id"],
            "occurred_at": str(row["occurred_at"]),
            "policy_version": str(row["policy_version"] or MemoryScorePolicy.version),
        }
        for row in rows
    )


def _retention_fold_tokens(
    rows: Iterable[sqlite3.Row],
) -> tuple[dict[str, object], ...]:
    """Canonical immutable fields used to audit a retention fold."""
    return tuple(
        {
            "receipt_id": str(row["receipt_id"]),
            "target_kind": str(row["target_kind"]),
            "target_id": str(row["target_id"]),
            "occurred_at": str(row["occurred_at"]),
            "outcome_kind": str(row["outcome_kind"]),
            "source_ref": str(row["source_ref"]),
            "recall_revision": row["recall_revision"],
            "policy_version": str(row["policy_version"] or MemoryScorePolicy.version),
        }
        for row in rows
    )


def _retention_target_table(target_kind: str) -> tuple[str, str]:
    tables = {
        "episode": ("episodes", "episode_id"),
        "node": ("nodes", "node_id"),
        "assertion": ("assertions", "assertion_id"),
    }
    try:
        return tables[target_kind]
    except KeyError as exc:
        raise ValueError(f"unsupported retention target kind: {target_kind}") from exc


def _retention_target_is_active(target_kind: str, row: sqlite3.Row) -> bool:
    if target_kind == "node":
        return row["status"] in {"active", "candidate", "unresolved"}
    return row["lifecycle"] == "active"


def _timestamp_text(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            if text.isdigit() and len(text) == 4:
                parsed = datetime(int(text), 1, 1)
            else:
                raise ValueError(f"invalid timestamp: {value!r}") from None
    else:
        raise TypeError("timestamp must be datetime or ISO string")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _parse_utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _projection_revision(projection: ConsolidationProjection) -> str:
    payload = {
        "episode_id": projection.episode_id,
        "source_version": projection.source_version,
        "source_sha256": projection.source_sha256,
        "nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "label": node.canonical_label,
                "description": node.description,
                "scope": node.scope,
                "status": node.status,
                "confidence": node.confidence,
                "initial_confidence": node.initial_confidence,
                "prior_weight": node.prior_weight,
                "importance": node.importance,
                "initial_importance": node.initial_importance,
                "retention_days": node.retention_days,
                "retention_class": node.retention_class,
                "importance_event_class": node.importance_event_class,
                "properties": dict(node.properties),
            }
            for node in projection.nodes
        ],
        "aliases": [
            {
                "node_id": alias.node_id,
                "alias": alias.alias,
                "scope": alias.scope,
                "evidence_id": alias.evidence_id,
                "confidence": alias.confidence,
            }
            for alias in projection.aliases
        ],
        "descriptions": [
            {
                "node_id": description.node_id,
                "text": description.text,
                "language": description.language,
                "kind": description.kind,
                "evidence_id": description.evidence_id,
                "confidence": description.confidence,
            }
            for description in projection.descriptions
        ],
        "mentions": [
            {
                "episode_id": mention.episode_id,
                "surface_text": mention.surface_text,
                "node_id": mention.node_id,
                "resolution_state": mention.resolution_state,
                "role": mention.role,
                "span_start": mention.span_start,
                "span_end": mention.span_end,
                "confidence": mention.confidence,
                "evidence_id": mention.evidence_id,
            }
            for mention in projection.mentions
        ],
        "assertions": [
            {
                "id": assertion.assertion_id or _assertion_fingerprint(assertion),
                "subject_id": assertion.subject_id,
                "predicate": assertion.predicate,
                "object_node_id": assertion.object_node_id,
                "object_literal": assertion.object_literal,
                "object_unit": assertion.object_unit,
                "polarity": assertion.polarity,
                "epistemic_status": assertion.epistemic_status,
                "viewpoint": assertion.viewpoint,
                "context": assertion.context,
                "valid_from": assertion.valid_from,
                "valid_to": assertion.valid_to,
                "confidence": assertion.confidence,
                "initial_confidence": assertion.initial_confidence,
                "prior_weight": assertion.prior_weight,
                "importance": assertion.importance,
                "initial_importance": assertion.initial_importance,
                "retention_days": assertion.retention_days,
                "retention_class": assertion.retention_class,
                "importance_event_class": assertion.importance_event_class,
                "conflict_group": assertion.conflict_group,
                "supersedes_assertion_id": assertion.supersedes_assertion_id,
                "evidence_ids": list(assertion.evidence_ids),
                "object_literal_type": assertion.object_literal_type,
                "predicate_registry_version": assertion.predicate_registry_version,
                "policy_version": assertion.policy_version,
                "genesis_submission_id": assertion.genesis_submission_id,
            }
            for assertion in projection.assertions
        ],
        "evidence": [
            {
                "evidence_id": evidence.evidence_id,
                "source_type": evidence.source_type,
                "source_id": evidence.source_id,
                "excerpt": evidence.excerpt,
                "media_locator": evidence.media_locator,
                "modality": evidence.modality,
                "span_start": evidence.span_start,
                "span_end": evidence.span_end,
                "speaker": evidence.speaker,
                "viewpoint": evidence.viewpoint,
                "captured_at": evidence.captured_at,
                "extraction_run_id": evidence.extraction_run_id,
                "source_sha256": evidence.source_sha256,
                "source_version": evidence.source_version,
                "attribution": evidence.attribution,
                "independence_key": evidence.independence_key,
                "source_reliability_class": evidence.source_reliability_class,
                "source_policy_version": evidence.source_policy_version,
                "genesis_submission_id": evidence.genesis_submission_id,
            }
            for evidence in projection.evidence
        ],
        "assertion_evidence": [
            {
                "assertion_id": link.assertion_id,
                "evidence_id": link.evidence_id,
                "stance": link.stance,
            }
            for link in projection.assertion_evidence
        ],
        "extraction_run_id": projection.extraction_run_id,
    }
    return (
        "projection:"
        + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    )


def _episode_facet_conditions(
    *,
    person_node_ids: Iterable[str],
    place_node_ids: Iterable[str],
    emotion_labels: Iterable[str],
    topic_labels: Iterable[str],
    cause_labels: Iterable[str],
    privacy_scope: str | None,
) -> tuple[list[str], list[Any]]:
    """Build positive AND-across-family/OR-within-family source filters."""
    conditions: list[str] = []
    params: list[Any] = []
    for node_type, values, _label in (
        ("person", tuple(dict.fromkeys(person_node_ids)), "person"),
        ("place", tuple(dict.fromkeys(place_node_ids)), "place"),
    ):
        if values:
            placeholders = ",".join("?" for _ in values)
            conditions.append(
                "EXISTS (SELECT 1 FROM episode_mentions AS fm "
                "JOIN nodes AS fn ON fn.node_id=fm.node_id "
                "WHERE fm.episode_id=p.episode_id AND fm.node_id IN ("
                + placeholders
                + ") AND fn.node_type=? AND fm.resolution_state='resolved')"
            )
            params.extend(values)
            params.append(node_type)
    if emotion_labels:
        values = tuple(dict.fromkeys(str(item).casefold() for item in emotion_labels))
        placeholders = ",".join("?" for _ in values)
        conditions.append(
            "lower(COALESCE(json_extract(p.metadata_json, '$.emotion'), '')) IN ("
            + placeholders
            + ")"
        )
        params.extend(values)
    for raw_values, column in (
        (topic_labels, "topic"),
        (cause_labels, "cause"),
    ):
        normalized = tuple(dict.fromkeys(str(item).casefold() for item in raw_values))
        if normalized:
            conditions.append(
                "("
                + " OR ".join(
                    "lower(COALESCE(json_extract(p.metadata_json, '$."
                    + column
                    + "'), '')) LIKE ?"
                    for _ in normalized
                )
                + ")"
            )
            params.extend("%" + value + "%" for value in normalized)
    if privacy_scope is not None:
        conditions.append("p.privacy_scope=?")
        params.append(privacy_scope)
    return conditions, params


__all__ = ["SQLiteGraphStoreMixin"]
