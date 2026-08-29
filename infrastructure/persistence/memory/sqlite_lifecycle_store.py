"""Lifecycle maintenance for source-first SQLite Memory."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

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
        """Return whether any historical record is currently due for review."""
        now = utc_now()
        with self._lock:
            episode_scope = ""
            episode_params: list[object] = [now]
            if getattr(self, "elfie_id", None) is not None:
                episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                episode_params.append(str(self.elfie_id))
            episode_visibility, episode_visibility_params = self._genesis_visibility(
                "e"
            )
            episode_params.extend(episode_visibility_params)
            episode = self.conn.execute(
                """SELECT 1 FROM episodes AS e
                   WHERE e.lifecycle <> 'forgotten'
                     AND (e.next_review_at IS NULL OR e.next_review_at <= ?)"""
                + episode_scope
                + " AND "
                + episode_visibility
                + " LIMIT 1",
                episode_params,
            ).fetchone()
            if episode is not None:
                return True

            node_scope = ""
            node_params: list[object] = [now]
            if getattr(self, "elfie_id", None) is not None:
                node_scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                node_params.append(str(self.elfie_id))
            node_visibility, node_visibility_params = self._genesis_visibility("n")
            node_params.extend(node_visibility_params)
            node = self.conn.execute(
                """SELECT 1 FROM nodes AS n
                   WHERE n.status <> 'forgotten' AND n.merged_into IS NULL
                     AND (n.next_review_at IS NULL OR n.next_review_at <= ?)"""
                + node_scope
                + " AND "
                + node_visibility
                + " LIMIT 1",
                node_params,
            ).fetchone()
            if node is not None:
                return True

            assertion_scope = ""
            assertion_params: list[object] = [now]
            if getattr(self, "elfie_id", None) is not None:
                assertion_scope = (
                    " AND EXISTS (SELECT 1 FROM nodes AS an "
                    "WHERE an.node_id=a.subject_node_id "
                    "AND json_extract(an.properties_json, '$.elfie_id')=?)"
                )
                assertion_params.append(str(self.elfie_id))
            assertion_visibility, assertion_visibility_params = (
                self._genesis_visibility("a")
            )
            assertion_params.extend(assertion_visibility_params)
            return (
                self.conn.execute(
                    """SELECT 1 FROM assertions AS a
                       WHERE a.lifecycle='active'
                         AND (a.next_review_at IS NULL OR a.next_review_at <= ?)"""
                    + assertion_scope
                    + " AND "
                    + assertion_visibility
                    + " LIMIT 1",
                    assertion_params,
                ).fetchone()
                is not None
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

    conn: sqlite3.Connection

    def run_lifecycle(self, request: MaintenanceRequest) -> MaintenanceReceipt:
        now = utc_now()
        worker = request.worker_id
        episode_ids: list[str] = []
        node_ids: list[str] = []
        assertion_ids: list[str] = []
        errors: dict[str, str] = {}
        processed_count = 0
        checkpoint_blocked = False
        checkpoint_stage, checkpoint_target = _decode_checkpoint(request.checkpoint)
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                self._recover_expired_maintenance_leases_locked(now)
                episode_scope = ""
                episode_params: list[object] = [now]
                if getattr(self, "elfie_id", None) is not None:
                    episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                    episode_params.append(str(self.elfie_id))
                episode_visibility, episode_visibility_params = (
                    self._genesis_visibility("e")
                )
                episode_params.extend(episode_visibility_params)
                episode_params.append(request.max_episodes * 2)
                rows = self.conn.execute(
                    """SELECT e.*,
                              (SELECT COUNT(*) FROM evidence AS ev
                                WHERE ev.source_type='episode'
                                  AND ev.source_id=e.episode_id) AS evidence_count,
                              (SELECT COUNT(*) FROM evidence AS ev
                                WHERE ev.source_type='episode'
                                  AND ev.source_id=e.episode_id
                                  AND (ev.source_sha256 IS NULL
                                       OR ev.source_sha256 <> e.content_sha256))
                                AS ungrounded_evidence_count
                       FROM episodes AS e
                       WHERE e.lifecycle <> 'forgotten'
                         AND (e.next_review_at IS NULL OR e.next_review_at <= ?)"""
                    + episode_scope
                    + " AND "
                    + episode_visibility
                    + " ORDER BY COALESCE(e.next_review_at, e.occurred_from, e.updated_at), e.episode_id LIMIT ?",
                    episode_params,
                ).fetchall()
                for row in rows:
                    if processed_count >= request.max_episodes:
                        break
                    episode_id = str(row["episode_id"])
                    if not _checkpoint_allows(
                        checkpoint_stage,
                        checkpoint_target,
                        "episode",
                        episode_id,
                    ):
                        continue
                    claim_attempt = self._claim_maintenance_target(
                        stage="lifecycle",
                        target_id=episode_id,
                        worker=worker,
                        now=now,
                        lease_seconds=request.lease_seconds,
                        checkpoint=request.checkpoint,
                    )
                    if claim_attempt is None:
                        continue
                    processed_count += 1
                    try:
                        projected = (
                            row["projection_revision"] is not None
                            and row["projection_source_sha256"] == row["content_sha256"]
                        )
                        old_detail = str(row["detail_level"])
                        new_detail = old_detail
                        old_lifecycle = str(row["lifecycle"])
                        new_lifecycle = old_lifecycle
                        summary = row["summary_text"] or str(row["content_text"])[:512]
                        content = str(row["content_text"])
                        new_importance = MemoryScorePolicy.decay_importance(
                            float(row["importance"])
                        )
                        # Never compact an Episode that has not been projected
                        # for its current source hash.
                        if projected:
                            if old_lifecycle == "archived" and _can_forget_episode(
                                row, new_importance
                            ):
                                new_lifecycle = "forgotten"
                                new_detail = "digest"
                                content = f"[forgotten:{row['content_sha256']}]"
                                summary = None
                            elif old_detail == "full":
                                new_detail = "compressed"
                            elif old_detail == "compressed":
                                new_detail = "digest"
                                content = f"[digest:{row['content_sha256']}]"
                            elif old_detail == "digest":
                                new_lifecycle = "archived"
                        next_review = (
                            None
                            if new_lifecycle == "forgotten"
                            else _next_review(now, new_detail, new_lifecycle)
                        )
                        changed = self.conn.execute(
                            """UPDATE episodes SET importance=?,
                                   content_text=?, summary_text=?, detail_level=?,
                                   lifecycle=?, last_reviewed_at=?, next_review_at=?,
                                   policy_version='memory.v1', updated_at=?
                               WHERE episode_id=?
                                 AND """
                            + _maintenance_claim_predicate(),
                            (
                                new_importance,
                                content,
                                summary,
                                new_detail,
                                new_lifecycle,
                                now,
                                next_review,
                                now,
                                episode_id,
                                str(getattr(self, "elfie_id", "") or ""),
                                "lifecycle",
                                episode_id,
                                worker,
                                claim_attempt,
                                now,
                            ),
                        ).rowcount
                        if changed != 1:
                            raise RuntimeError(
                                "lifecycle claim was lost before Episode update"
                            )
                        self._upsert_episode_fts_from_values(
                            episode_id,
                            content,
                            summary,
                        )
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=episode_id,
                            state="completed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            attempt=claim_attempt,
                        )
                        episode_ids.append(episode_id)
                        if not checkpoint_blocked:
                            checkpoint_stage, checkpoint_target = "episode", episode_id
                    except Exception as error:  # noqa: BLE001
                        errors[episode_id] = str(error)
                        checkpoint_blocked = True
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=episode_id,
                            state="failed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            error=str(error),
                            attempt=claim_attempt,
                        )
                remaining = max(0, request.max_episodes - processed_count)
                node_visibility, node_visibility_params = self._genesis_visibility("n")
                node_scope = ""
                node_params: list[object] = [now]
                if getattr(self, "elfie_id", None) is not None:
                    node_scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                    node_params.append(str(self.elfie_id))
                node_params.extend(node_visibility_params)
                node_params.append(max(0, remaining) * 2)
                node_rows = (
                    self.conn.execute(
                        """SELECT n.node_id FROM nodes AS n
                       WHERE n.status <> 'forgotten' AND n.merged_into IS NULL
                         AND (n.next_review_at IS NULL OR n.next_review_at <= ?)"""
                        + node_scope
                        + " AND "
                        + node_visibility
                        + " ORDER BY COALESCE(n.next_review_at, n.updated_at), n.node_id LIMIT ?",
                        node_params,
                    ).fetchall()
                    if remaining
                    else ()
                )
                for row in node_rows:
                    if processed_count >= request.max_episodes:
                        break
                    node_id = str(row["node_id"])
                    if not _checkpoint_allows(
                        checkpoint_stage,
                        checkpoint_target,
                        "node",
                        node_id,
                    ):
                        continue
                    claim_attempt = self._claim_maintenance_target(
                        stage="lifecycle",
                        target_id=node_id,
                        worker=worker,
                        now=now,
                        lease_seconds=request.lease_seconds,
                        checkpoint=request.checkpoint,
                    )
                    if claim_attempt is None:
                        continue
                    processed_count += 1
                    try:
                        changed = self.conn.execute(
                            """UPDATE nodes SET importance=MAX(0.0, importance-?),
                                   last_reviewed_at=?, next_review_at=?,
                                   policy_version='memory.v1', updated_at=? WHERE node_id=?
                                 AND """
                            + _maintenance_claim_predicate(),
                            (
                                MemoryScorePolicy.lifecycle_decay,
                                now,
                                _next_review(now, "", "active"),
                                now,
                                node_id,
                                str(getattr(self, "elfie_id", "") or ""),
                                "lifecycle",
                                node_id,
                                worker,
                                claim_attempt,
                                now,
                            ),
                        ).rowcount
                        if changed != 1:
                            raise RuntimeError(
                                "lifecycle claim was lost before Node update"
                            )
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=node_id,
                            state="completed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            attempt=claim_attempt,
                        )
                        node_ids.append(node_id)
                    except Exception as error:  # noqa: BLE001
                        errors[node_id] = str(error)
                        checkpoint_blocked = True
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=node_id,
                            state="failed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            error=str(error),
                            attempt=claim_attempt,
                        )
                    else:
                        if not checkpoint_blocked:
                            checkpoint_stage, checkpoint_target = "node", node_id

                remaining = max(0, request.max_episodes - processed_count)
                assertion_visibility, assertion_visibility_params = (
                    self._genesis_visibility("a")
                )
                assertion_scope = ""
                assertion_scope_params: list[object] = []
                if getattr(self, "elfie_id", None) is not None:
                    assertion_scope = (
                        " AND EXISTS (SELECT 1 FROM nodes AS an "
                        "WHERE an.node_id=a.subject_node_id "
                        "AND json_extract(an.properties_json, '$.elfie_id')=?)"
                    )
                    assertion_scope_params.append(str(self.elfie_id))
                assertion_params: list[object] = [
                    now,
                    *assertion_visibility_params,
                    *assertion_scope_params,
                    remaining * 2,
                ]
                assertion_rows = (
                    self.conn.execute(
                        """SELECT a.assertion_id FROM assertions AS a
                       WHERE a.lifecycle='active'
                         AND (a.next_review_at IS NULL OR a.next_review_at <= ?)
                         AND """
                        + assertion_visibility
                        + assertion_scope
                        + " ORDER BY COALESCE(a.next_review_at, a.updated_at), a.assertion_id LIMIT ?",
                        assertion_params,
                    ).fetchall()
                    if remaining
                    else ()
                )
                for row in assertion_rows:
                    if processed_count >= request.max_episodes:
                        break
                    assertion_id = str(row["assertion_id"])
                    if not _checkpoint_allows(
                        checkpoint_stage,
                        checkpoint_target,
                        "assertion",
                        assertion_id,
                    ):
                        continue
                    claim_attempt = self._claim_maintenance_target(
                        stage="lifecycle",
                        target_id=assertion_id,
                        worker=worker,
                        now=now,
                        lease_seconds=request.lease_seconds,
                        checkpoint=request.checkpoint,
                    )
                    if claim_attempt is None:
                        continue
                    processed_count += 1
                    try:
                        changed = self.conn.execute(
                            """UPDATE assertions SET importance=MAX(0.0, importance-?),
                                   last_reviewed_at=?, next_review_at=?,
                                   policy_version='memory.v1', updated_at=?
                               WHERE assertion_id=? AND """
                            + (
                                "EXISTS (SELECT 1 FROM nodes AS an "
                                "WHERE an.node_id=assertions.subject_node_id "
                                "AND json_extract(an.properties_json, '$.elfie_id')=?)"
                                if getattr(self, "elfie_id", None) is not None
                                else ""
                            )
                            + (
                                " AND "
                                if getattr(self, "elfie_id", None) is not None
                                else ""
                            )
                            + _maintenance_claim_predicate(),
                            (
                                MemoryScorePolicy.lifecycle_decay,
                                now,
                                _next_review(now, "", "active"),
                                now,
                                assertion_id,
                                *(
                                    (str(self.elfie_id),)
                                    if getattr(self, "elfie_id", None) is not None
                                    else ()
                                ),
                                str(getattr(self, "elfie_id", "") or ""),
                                "lifecycle",
                                assertion_id,
                                worker,
                                claim_attempt,
                                now,
                            ),
                        ).rowcount
                        if changed != 1:
                            raise RuntimeError(
                                "lifecycle claim was lost before Assertion update"
                            )
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=assertion_id,
                            state="completed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            attempt=claim_attempt,
                        )
                        assertion_ids.append(assertion_id)
                    except Exception as error:  # noqa: BLE001
                        errors[assertion_id] = str(error)
                        checkpoint_blocked = True
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=assertion_id,
                            state="failed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            error=str(error),
                            attempt=claim_attempt,
                        )
                    else:
                        if not checkpoint_blocked:
                            checkpoint_stage, checkpoint_target = (
                                "assertion",
                                assertion_id,
                            )

                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        status = (
            "failed"
            if errors and not (episode_ids or node_ids or assertion_ids)
            else ("partial" if errors else "completed")
        )
        if not (episode_ids or node_ids or assertion_ids) and not errors:
            status = "empty"
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


def _next_review(now: str, detail_level: str, lifecycle: str) -> str:
    if lifecycle == "archived":
        days = 90
    elif detail_level == "compressed":
        days = 30
    elif detail_level == "digest":
        days = 60
    else:
        days = 7
    current = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (current + timedelta(days=days)).isoformat(timespec="milliseconds")


def _can_forget_episode(row: sqlite3.Row, importance: float) -> bool:
    """Apply the source-safety gate for automatic archived-source forgetting."""
    if str(row["detail_level"]) != "digest":
        return False
    if row["projection_revision"] is None or (
        row["projection_source_sha256"] != row["content_sha256"]
    ):
        return False
    if int(row["evidence_count"] or 0) < 1:
        return False
    if int(row["ungrounded_evidence_count"] or 0) > 0:
        return False
    return MemoryScorePolicy.can_forget(importance)


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
