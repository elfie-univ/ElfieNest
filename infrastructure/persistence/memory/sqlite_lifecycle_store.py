"""Lifecycle maintenance for source-first SQLite Memory."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from elfie.brain.memory.memory_records import (
    MaintenanceReceipt,
    MaintenanceRequest,
)
from elfie.brain.memory.score_policy import MemoryScorePolicy

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import canonical_json, utc_now


class SQLiteLifecycleStoreMixin(SQLiteMemoryMixinBase):
    """Apply bounded, deterministic importance/detail lifecycle policy."""

    def has_due_lifecycle(self) -> bool:
        """Return whether a score-derived lifecycle transition is ready."""
        now = utc_now()
        with self._lock:
            episode_rows = self._lifecycle_episode_rows_locked()
            if any(_episode_transition(row, now) is not None for row in episode_rows):
                return True
            node_rows = self._lifecycle_node_rows_locked()
            if any(_node_transition(row, now) is not None for row in node_rows):
                return True
            assertion_rows = self._lifecycle_assertion_rows_locked()
            return any(
                _assertion_transition(row, now) is not None for row in assertion_rows
            )

    def recover_expired_maintenance_leases(self) -> int:
        """Make abandoned Lifecycle work immediately retryable."""
        now = utc_now()
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                changed = self._recover_expired_maintenance_leases_locked(now)
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return changed

    def _lifecycle_episode_rows_locked(self) -> list[sqlite3.Row]:
        scope = ""
        params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
            params.append(str(self.elfie_id))
        visibility, visibility_params = self._genesis_visibility("e")
        params.extend(visibility_params)
        return self.conn.execute(
            """SELECT e.*,
                      (SELECT COUNT(*) FROM evidence AS ev
                        WHERE ev.source_type='episode' AND ev.source_id=e.episode_id) AS evidence_count,
                      (SELECT COUNT(*) FROM evidence AS ev
                        WHERE ev.source_type='episode' AND ev.source_id=e.episode_id
                          AND (ev.source_sha256 IS NULL OR ev.source_sha256 <> e.content_sha256))
                        AS ungrounded_evidence_count
                 FROM episodes AS e
                WHERE e.lifecycle <> 'forgotten'"""
            + scope
            + " AND "
            + visibility
            + " ORDER BY e.episode_id",
            params,
        ).fetchall()

    def _lifecycle_node_rows_locked(self) -> list[sqlite3.Row]:
        scope = ""
        params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
            params.append(str(self.elfie_id))
        visibility, visibility_params = self._genesis_visibility("n")
        params.extend(visibility_params)
        return self.conn.execute(
            """SELECT n.*,
                      (SELECT COUNT(*) FROM assertions AS a
                        WHERE a.lifecycle='active'
                          AND (a.subject_node_id=n.node_id OR a.object_node_id=n.node_id))
                        AS active_assertion_count
                 FROM nodes AS n
                WHERE n.status <> 'forgotten' AND n.merged_into IS NULL"""
            + scope
            + " AND "
            + visibility
            + " ORDER BY n.node_id",
            params,
        ).fetchall()

    def _lifecycle_assertion_rows_locked(self) -> list[sqlite3.Row]:
        scope = ""
        params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            scope = (
                " AND EXISTS (SELECT 1 FROM nodes AS an "
                "WHERE an.node_id=a.subject_node_id "
                "AND json_extract(an.properties_json, '$.elfie_id')=?)"
            )
            params.append(str(self.elfie_id))
        visibility, visibility_params = self._genesis_visibility("a")
        params.extend(visibility_params)
        return self.conn.execute(
            """SELECT a.*,
                      (SELECT COUNT(*) FROM assertion_evidence AS ae
                        WHERE ae.assertion_id=a.assertion_id) AS evidence_count
                 FROM assertions AS a
                WHERE a.lifecycle NOT IN ('forgotten', 'superseded')"""
            + scope
            + " AND "
            + visibility
            + " ORDER BY a.assertion_id",
            params,
        ).fetchall()

    conn: sqlite3.Connection

    def run_lifecycle(self, request: MaintenanceRequest) -> MaintenanceReceipt:
        now = utc_now()
        worker = request.worker_id
        episode_ids: list[str] = []
        node_ids: list[str] = []
        assertion_ids: list[str] = []
        errors: dict[str, str] = {}
        processed = 0
        checkpoint_blocked = False
        checkpoint_stage, checkpoint_target = _decode_checkpoint(request.checkpoint)

        def claim(stage: str, target_id: str) -> int | None:
            return self._claim_maintenance_target(
                stage=stage,
                target_id=target_id,
                worker=worker,
                now=now,
                lease_seconds=request.lease_seconds,
                checkpoint=request.checkpoint,
            )

        def record_failure(target_id: str, attempt: int, error: Exception) -> None:
            errors[target_id] = str(error)
            self._record_maintenance(
                stage="lifecycle",
                target_id=target_id,
                state="failed",
                worker=worker,
                now=now,
                checkpoint=request.checkpoint,
                error=str(error),
                attempt=attempt,
            )

        with self._lock:
            owns = self._begin_write_transaction()
            try:
                self._recover_expired_maintenance_leases_locked(now)
                for row in self._lifecycle_episode_rows_locked():
                    if processed >= request.max_episodes:
                        break
                    transition = _episode_transition(row, now)
                    target_id = str(row["episode_id"])
                    if transition is None or not _checkpoint_allows(
                        checkpoint_stage, checkpoint_target, "episode", target_id
                    ):
                        continue
                    attempt = claim("lifecycle", target_id)
                    if attempt is None:
                        continue
                    processed += 1
                    try:
                        detail, lifecycle, content, summary = transition
                        anchor = str(
                            row["last_reinforced_at"] or row["updated_at"] or now
                        )
                        next_review = _next_lifecycle_review(
                            anchor,
                            float(row["half_life_days"]),
                            detail,
                            lifecycle,
                        )
                        changed = self.conn.execute(
                            """UPDATE episodes SET content_text=?, summary_text=?, detail_level=?,
                                   lifecycle=?, last_reviewed_at=?, next_review_at=?,
                                   lifecycle_changed_at=CASE WHEN lifecycle<>? THEN ? ELSE lifecycle_changed_at END,
                                   policy_version=?, updated_at=? WHERE episode_id=? AND """
                            + _maintenance_claim_predicate(),
                            (
                                content,
                                summary,
                                detail,
                                lifecycle,
                                now,
                                next_review,
                                lifecycle,
                                now,
                                MemoryScorePolicy.version,
                                now,
                                target_id,
                                str(getattr(self, "elfie_id", "") or ""),
                                "lifecycle",
                                target_id,
                                worker,
                                attempt,
                                now,
                            ),
                        ).rowcount
                        if changed != 1:
                            raise RuntimeError(
                                "lifecycle claim was lost before Episode update"
                            )
                        self._upsert_episode_fts_from_values(
                            target_id, content, summary
                        )
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=target_id,
                            state="completed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            attempt=attempt,
                        )
                        episode_ids.append(target_id)
                        if not checkpoint_blocked:
                            checkpoint_stage, checkpoint_target = "episode", target_id
                    except Exception as error:  # noqa: BLE001
                        checkpoint_blocked = True
                        record_failure(target_id, attempt, error)

                for row in self._lifecycle_node_rows_locked():
                    if processed >= request.max_episodes:
                        break
                    target_id = str(row["node_id"])
                    node_lifecycle = _node_transition(row, now)
                    if node_lifecycle is None or not _checkpoint_allows(
                        checkpoint_stage, checkpoint_target, "node", target_id
                    ):
                        continue
                    attempt = claim("lifecycle", target_id)
                    if attempt is None:
                        continue
                    processed += 1
                    try:
                        lifecycle = node_lifecycle
                        changed = self.conn.execute(
                            """UPDATE nodes SET status=?, last_reviewed_at=?, next_review_at=NULL,
                                   lifecycle_changed_at=CASE WHEN status<>? THEN ? ELSE lifecycle_changed_at END,
                                   policy_version=?, updated_at=? WHERE node_id=? AND """
                            + _maintenance_claim_predicate(),
                            (
                                lifecycle,
                                now,
                                lifecycle,
                                now,
                                MemoryScorePolicy.version,
                                now,
                                target_id,
                                str(getattr(self, "elfie_id", "") or ""),
                                "lifecycle",
                                target_id,
                                worker,
                                attempt,
                                now,
                            ),
                        ).rowcount
                        if changed != 1:
                            raise RuntimeError(
                                "lifecycle claim was lost before Node update"
                            )
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=target_id,
                            state="completed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            attempt=attempt,
                        )
                        node_ids.append(target_id)
                        if not checkpoint_blocked:
                            checkpoint_stage, checkpoint_target = "node", target_id
                    except Exception as error:  # noqa: BLE001
                        checkpoint_blocked = True
                        record_failure(target_id, attempt, error)

                for row in self._lifecycle_assertion_rows_locked():
                    if processed >= request.max_episodes:
                        break
                    target_id = str(row["assertion_id"])
                    assertion_lifecycle = _assertion_transition(row, now)
                    if assertion_lifecycle is None or not _checkpoint_allows(
                        checkpoint_stage, checkpoint_target, "assertion", target_id
                    ):
                        continue
                    attempt = claim("lifecycle", target_id)
                    if attempt is None:
                        continue
                    processed += 1
                    try:
                        lifecycle = assertion_lifecycle
                        changed = self.conn.execute(
                            """UPDATE assertions SET lifecycle=?, last_reviewed_at=?, next_review_at=NULL,
                                   lifecycle_changed_at=CASE WHEN lifecycle<>? THEN ? ELSE lifecycle_changed_at END,
                                   policy_version=?, updated_at=? WHERE assertion_id=? AND """
                            + _maintenance_claim_predicate(),
                            (
                                lifecycle,
                                now,
                                lifecycle,
                                now,
                                MemoryScorePolicy.version,
                                now,
                                target_id,
                                str(getattr(self, "elfie_id", "") or ""),
                                "lifecycle",
                                target_id,
                                worker,
                                attempt,
                                now,
                            ),
                        ).rowcount
                        if changed != 1:
                            raise RuntimeError(
                                "lifecycle claim was lost before Assertion update"
                            )
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=target_id,
                            state="completed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            attempt=attempt,
                        )
                        assertion_ids.append(target_id)
                        if not checkpoint_blocked:
                            checkpoint_stage, checkpoint_target = "assertion", target_id
                    except Exception as error:  # noqa: BLE001
                        checkpoint_blocked = True
                        record_failure(target_id, attempt, error)
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        status = (
            "failed"
            if errors and not (episode_ids or node_ids or assertion_ids)
            else "partial"
            if errors
            else "completed"
            if (episode_ids or node_ids or assertion_ids)
            else "empty"
        )
        checkpoint = _encode_checkpoint(
            checkpoint_stage,
            checkpoint_target,
            fallback=request.checkpoint or f"maintenance:{worker}:{now}",
        )
        return MaintenanceReceipt(
            worker_id=worker,
            status=status,  # type: ignore[arg-type]
            lifecycle_episode_ids=tuple(episode_ids),
            lifecycle_node_ids=tuple(node_ids),
            lifecycle_assertion_ids=tuple(assertion_ids),
            checkpoint=checkpoint,
            errors=errors,
        )

    def inspect_episode(self, episode_id: str):
        return self.get_episode(episode_id)

    def _claim_maintenance_target(
        self,
        *,
        stage: str,
        target_id: str,
        worker: str,
        now: str,
        lease_seconds: int,
        checkpoint: str | None,
    ) -> int | None:
        """Claim one Lifecycle target with an expiring operational lease."""
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        row = self.conn.execute(
            """SELECT state, lease_owner, lease_until, next_attempt_at, attempts
                 FROM memory_maintenance
                WHERE elfie_id=? AND stage=? AND target_id=?""",
            (elfie_id, stage, target_id),
        ).fetchone()
        if row is not None:
            lease_until = row["lease_until"]
            if (
                str(row["state"]) == "processing"
                and lease_until is not None
                and str(lease_until) > now
                and str(row["lease_owner"] or "") != worker
            ):
                return None
            next_attempt = row["next_attempt_at"]
            if next_attempt is not None and str(next_attempt) > now:
                return None
        attempt = 1 if row is None else int(row["attempts"] or 0) + 1
        lease_until = (
            datetime.fromisoformat(now.replace("Z", "+00:00"))
            + timedelta(seconds=max(1, lease_seconds))
        ).isoformat(timespec="milliseconds")
        work_id = f"{elfie_id}:{stage}:{target_id}"
        self.conn.execute(
            """INSERT INTO memory_maintenance(
                   work_id, elfie_id, stage, target_id, state, attempts,
                   lease_owner, lease_until, checkpoint_json, updated_at
               ) VALUES (?, ?, ?, ?, 'processing', 1, ?, ?, ?, ?)
               ON CONFLICT(elfie_id, stage, target_id) DO UPDATE SET
                   state='processing', attempts=memory_maintenance.attempts+1,
                   lease_owner=excluded.lease_owner, lease_until=excluded.lease_until,
                   next_attempt_at=NULL, last_error=NULL,
                   checkpoint_json=excluded.checkpoint_json,
                   updated_at=excluded.updated_at""",
            (
                work_id,
                elfie_id,
                stage,
                target_id,
                worker,
                lease_until,
                canonical_json({"checkpoint": checkpoint} if checkpoint else {}),
                now,
            ),
        )
        return attempt

    def _recover_expired_maintenance_leases_locked(self, now: str) -> int:
        """Recover expired Lifecycle leases inside the caller's transaction."""
        scope = ""
        params: list[object] = [now, now, now]
        if getattr(self, "elfie_id", None) is not None:
            scope = " AND elfie_id=?"
            params.append(str(self.elfie_id))
        cursor = self.conn.execute(
            """UPDATE memory_maintenance SET state='failed', lease_owner=NULL,
                   lease_until=NULL, next_attempt_at=?,
                   last_error=COALESCE(last_error, 'maintenance lease expired'),
                   updated_at=?
               WHERE stage='lifecycle' AND state='processing'
                 AND (lease_until IS NULL OR lease_until < ?)"""
            + scope,
            params,
        )
        return cursor.rowcount

    def _record_maintenance(
        self,
        *,
        stage: str,
        target_id: str,
        state: str,
        worker: str,
        now: str,
        checkpoint: str | None = None,
        error: str | None = None,
        attempt: int | None = None,
    ) -> None:
        if attempt is None:
            raise ValueError("attempt is required when recording Lifecycle work")
        elfie_id = str(getattr(self, "elfie_id", "") or "")
        claim = self.conn.execute(
            """SELECT state, lease_owner, lease_until, attempts
                 FROM memory_maintenance
                WHERE elfie_id=? AND stage=? AND target_id=?""",
            (elfie_id, stage, target_id),
        ).fetchone()
        if (
            claim is None
            or str(claim["state"]) != "processing"
            or str(claim["lease_owner"] or "") != worker
            or int(claim["attempts"] or 0) != attempt
            or claim["lease_until"] is None
            or str(claim["lease_until"]) <= now
        ):
            # A worker that lost its lease must not overwrite the retry state
            # written by a newer claimant.
            return
        retry_at = None
        if state == "failed":
            retry_at = (
                datetime.fromisoformat(now.replace("Z", "+00:00"))
                + timedelta(seconds=30)
            ).isoformat(timespec="milliseconds")
        cursor = self.conn.execute(
            """UPDATE memory_maintenance SET state=?, lease_owner=NULL,
                   lease_until=NULL, next_attempt_at=?, last_error=?,
                   checkpoint_json=?, updated_at=?
               WHERE elfie_id=? AND stage=? AND target_id=?
                 AND state='processing' AND lease_owner=? AND attempts=?
                 AND lease_until>?""",
            (
                state,
                retry_at,
                error,
                canonical_json({"checkpoint": checkpoint} if checkpoint else {}),
                now,
                elfie_id,
                stage,
                target_id,
                worker,
                attempt,
                now,
            ),
        )
        if cursor.rowcount != 1:
            return


def _maintenance_claim_predicate() -> str:
    """Return the SQL predicate that fences a Lifecycle worker lease."""
    return """EXISTS (
        SELECT 1 FROM memory_maintenance AS mm
        WHERE mm.elfie_id=? AND mm.stage=? AND mm.target_id=?
          AND mm.state='processing' AND mm.lease_owner=?
          AND mm.attempts=? AND mm.lease_until>?
    )"""


def _row_freshness(row: sqlite3.Row, now: str) -> float:
    keys = set(row.keys())
    anchor = row["last_reinforced_at"] if "last_reinforced_at" in keys else None
    if not anchor and "updated_at" in keys:
        anchor = row["updated_at"]
    if not anchor and "created_at" in keys:
        anchor = row["created_at"]
    return MemoryScorePolicy.freshness(
        now,
        str(anchor or now),
        float(row["half_life_days"]),
    )


def _episode_transition(
    row: sqlite3.Row, now: str
) -> tuple[str, str, str, str | None] | None:
    """Return the next source-line lifecycle state, or ``None``."""
    lifecycle = str(row["lifecycle"])
    detail = str(row["detail_level"])
    freshness = _row_freshness(row, now)
    if lifecycle == "archived" and _can_forget_episode(row, freshness, now):
        return (
            "digest",
            "forgotten",
            f"[forgotten:{row['content_sha256']}]",
            None,
        )
    projected = (
        row["projection_revision"] is not None
        and row["projection_source_sha256"] == row["content_sha256"]
    )
    if not projected or lifecycle != "active":
        return None
    if detail == "full" and freshness <= MemoryScorePolicy.compress_freshness_threshold:
        content = str(row["content_text"])
        summary = row["summary_text"] or content[:512]
        return "compressed", "active", content, summary
    if (
        detail == "compressed"
        and freshness <= MemoryScorePolicy.digest_freshness_threshold
    ):
        return (
            "digest",
            "active",
            f"[digest:{row['content_sha256']}]",
            row["summary_text"] or str(row["content_text"])[:512],
        )
    if detail == "digest" and freshness < MemoryScorePolicy.active_freshness_threshold:
        return (
            "digest",
            "archived",
            str(row["content_text"]),
            row["summary_text"] or str(row["content_text"])[:512],
        )
    return None


def _node_transition(row: sqlite3.Row, now: str) -> str | None:
    status = str(row["status"])
    freshness = _row_freshness(row, now)
    if status == "archived":
        archived_at = row["lifecycle_changed_at"] or row["updated_at"] or now
        archived_days = _elapsed_days(str(archived_at), now)
        if MemoryScorePolicy.can_logically_forget(
            freshness=freshness,
            importance=float(row["importance"]),
            archived_days=archived_days,
            dependency_safe=int(row["active_assertion_count"] or 0) == 0,
        ):
            return "forgotten"
        return None
    if (
        status in {"active", "candidate", "unresolved"}
        and freshness < MemoryScorePolicy.active_freshness_threshold
    ):
        return "archived"
    return None


def _assertion_transition(row: sqlite3.Row, now: str) -> str | None:
    lifecycle = str(row["lifecycle"])
    freshness = _row_freshness(row, now)
    if lifecycle == "archived":
        archived_at = row["lifecycle_changed_at"] or row["updated_at"] or now
        if MemoryScorePolicy.can_logically_forget(
            freshness=freshness,
            importance=float(row["importance"]),
            archived_days=_elapsed_days(str(archived_at), now),
            dependency_safe=int(row["evidence_count"] or 0) == 0,
        ):
            return "forgotten"
        return None
    if (
        lifecycle == "active"
        and freshness < MemoryScorePolicy.active_freshness_threshold
    ):
        return "archived"
    return None


def _can_forget_episode(row: sqlite3.Row, freshness: float, now: str) -> bool:
    """Apply source/evidence safety before writing a logical forget marker."""
    if str(row["detail_level"]) != "digest":
        return False
    if (
        row["projection_revision"] is None
        or row["projection_source_sha256"] != row["content_sha256"]
    ):
        return False
    if (
        int(row["evidence_count"] or 0) < 1
        or int(row["ungrounded_evidence_count"] or 0) > 0
    ):
        return False
    archived_at = row["lifecycle_changed_at"] or row["updated_at"] or now
    return MemoryScorePolicy.can_logically_forget(
        freshness=freshness,
        importance=float(row["importance"]),
        archived_days=_elapsed_days(str(archived_at), now),
        dependency_safe=True,
    )


def _next_lifecycle_review(
    anchor: str, half_life_days: float, detail: str, lifecycle: str
) -> str | None:
    if lifecycle == "archived" or lifecycle == "forgotten":
        return None
    threshold = {
        "full": MemoryScorePolicy.compress_freshness_threshold,
        "compressed": MemoryScorePolicy.digest_freshness_threshold,
        "digest": MemoryScorePolicy.active_freshness_threshold,
    }.get(detail, MemoryScorePolicy.active_freshness_threshold)
    return MemoryScorePolicy.next_review_at(
        anchor, half_life_days, threshold
    ).isoformat(timespec="milliseconds")


def _elapsed_days(start: str, end: str) -> float:
    try:
        first = datetime.fromisoformat(start.replace("Z", "+00:00"))
        last = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return max(0.0, (last - first).total_seconds() / 86_400.0)


_CHECKPOINT_STAGE_ORDER = {"episode": 0, "node": 1, "assertion": 2}


def _decode_checkpoint(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    stage = payload.get("stage")
    target = payload.get("target_id")
    if stage not in _CHECKPOINT_STAGE_ORDER or not isinstance(target, str):
        return None, None
    return stage, target


def _checkpoint_allows(
    checkpoint_stage: str | None,
    checkpoint_target: str | None,
    stage: str,
    target_id: str,
) -> bool:
    if checkpoint_stage is None or checkpoint_target is None:
        return True
    stage_order = _CHECKPOINT_STAGE_ORDER[stage]
    checkpoint_order = _CHECKPOINT_STAGE_ORDER[checkpoint_stage]
    return stage_order > checkpoint_order or (
        stage_order == checkpoint_order and target_id > checkpoint_target
    )


def _encode_checkpoint(
    stage: str | None,
    target_id: str | None,
    *,
    fallback: str,
) -> str:
    if stage is None or target_id is None:
        return fallback
    return json.dumps(
        {"stage": stage, "target_id": target_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = ["SQLiteLifecycleStoreMixin"]
