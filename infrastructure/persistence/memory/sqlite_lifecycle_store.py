"""Lifecycle maintenance for source-first SQLite Memory."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from elfie.brain.memory.memory_records import (
    MaintenanceReceipt,
    MaintenanceRequest,
)

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import canonical_json, utc_now


class SQLiteLifecycleStoreMixin(SQLiteMemoryMixinBase):
    """Apply bounded, deterministic importance/detail lifecycle policy."""

    conn: sqlite3.Connection

    def run_lifecycle(self, request: MaintenanceRequest) -> MaintenanceReceipt:
        now = utc_now()
        worker = request.worker_id
        episode_ids: list[str] = []
        node_ids: list[str] = []
        assertion_ids: list[str] = []
        errors: dict[str, str] = {}
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                episode_scope = ""
                episode_params: list[object] = [now]
                if getattr(self, "elfie_id", None) is not None:
                    episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                    episode_params.append(str(self.elfie_id))
                episode_visibility, episode_visibility_params = (
                    self._genesis_visibility("e")
                )
                episode_params.extend(episode_visibility_params)
                episode_params.append(request.max_episodes)
                rows = self.conn.execute(
                    """SELECT e.* FROM episodes AS e
                       WHERE e.lifecycle='active'
                         AND (e.next_review_at IS NULL OR e.next_review_at <= ?)"""
                    + episode_scope
                    + " AND "
                    + episode_visibility
                    + " ORDER BY COALESCE(e.next_review_at, e.occurred_from, e.updated_at), e.episode_id LIMIT ?",
                    episode_params,
                ).fetchall()
                for row in rows:
                    episode_id = str(row["episode_id"])
                    try:
                        projected = (
                            row["projection_revision"] is not None
                            and row["projection_source_sha256"] == row["content_sha256"]
                        )
                        old_detail = str(row["detail_level"])
                        new_detail = old_detail
                        new_lifecycle = str(row["lifecycle"])
                        # Never compact an Episode that has not been projected
                        # for its current source hash.
                        if projected:
                            if old_detail == "full":
                                new_detail = "compressed"
                            elif old_detail == "compressed":
                                new_detail = "digest"
                            elif old_detail == "digest":
                                new_lifecycle = "archived"
                        next_review = _next_review(now, new_detail, new_lifecycle)
                        self.conn.execute(
                            """UPDATE episodes SET importance=MAX(0.0, importance-0.05),
                                   detail_level=?, lifecycle=?, last_reviewed_at=?,
                                   next_review_at=?, policy_version='memory.v1', updated_at=?
                               WHERE episode_id=?""",
                            (
                                new_detail,
                                new_lifecycle,
                                now,
                                next_review,
                                now,
                                episode_id,
                            ),
                        )
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=episode_id,
                            state="completed",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                        )
                        episode_ids.append(episode_id)
                    except Exception as error:  # noqa: BLE001
                        errors[episode_id] = str(error)
                        self._record_maintenance(
                            stage="lifecycle",
                            target_id=episode_id,
                            state="skipped",
                            worker=worker,
                            now=now,
                            checkpoint=request.checkpoint,
                            error=str(error),
                        )
                remaining = max(0, request.max_episodes - len(rows))
                node_visibility, node_visibility_params = self._genesis_visibility("n")
                node_scope = ""
                node_params: list[object] = [now]
                if getattr(self, "elfie_id", None) is not None:
                    node_scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                    node_params.append(str(self.elfie_id))
                node_params.extend(node_visibility_params)
                node_params.append(remaining)
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
                    node_id = str(row["node_id"])
                    self.conn.execute(
                        """UPDATE nodes SET importance=MAX(0.0, importance-0.05),
                               last_reviewed_at=?, next_review_at=?,
                               policy_version='memory.v1', updated_at=? WHERE node_id=?""",
                        (now, _next_review(now, "", "active"), now, node_id),
                    )
                    self._record_maintenance(
                        stage="lifecycle",
                        target_id=node_id,
                        state="completed",
                        worker=worker,
                        now=now,
                        checkpoint=request.checkpoint,
                    )
                    node_ids.append(node_id)

                remaining = max(0, request.max_episodes - len(rows) - len(node_rows))
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
                    remaining,
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
                    assertion_id = str(row["assertion_id"])
                    self.conn.execute(
                        """UPDATE assertions SET importance=MAX(0.0, importance-0.05),
                               last_reviewed_at=?, next_review_at=?,
                               policy_version='memory.v1', updated_at=?
                           WHERE assertion_id=?"""
                        + (
                            " AND EXISTS (SELECT 1 FROM nodes AS an "
                            "WHERE an.node_id=assertions.subject_node_id "
                            "AND json_extract(an.properties_json, '$.elfie_id')=?)"
                            if getattr(self, "elfie_id", None) is not None
                            else ""
                        ),
                        (
                            now,
                            _next_review(now, "", "active"),
                            now,
                            assertion_id,
                            *(
                                (str(self.elfie_id),)
                                if getattr(self, "elfie_id", None) is not None
                                else ()
                            ),
                        ),
                    )
                    self._record_maintenance(
                        stage="lifecycle",
                        target_id=assertion_id,
                        state="completed",
                        worker=worker,
                        now=now,
                        checkpoint=request.checkpoint,
                    )
                    assertion_ids.append(assertion_id)

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
        checkpoint = request.checkpoint or f"maintenance:{worker}:{now}"
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
    ) -> None:
        work_id = f"{getattr(self, 'elfie_id', '') or ''}:{stage}:{target_id}"
        self.conn.execute(
            """INSERT INTO memory_maintenance(
                   work_id, elfie_id, stage, target_id, state, attempts,
                   lease_owner, last_error, checkpoint_json, updated_at
               ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
               ON CONFLICT(elfie_id, stage, target_id) DO UPDATE SET
                   state=excluded.state, attempts=memory_maintenance.attempts+1,
                   lease_owner=excluded.lease_owner, last_error=excluded.last_error,
                   checkpoint_json=excluded.checkpoint_json,
                   updated_at=excluded.updated_at""",
            (
                work_id,
                str(getattr(self, "elfie_id", "") or ""),
                stage,
                target_id,
                state,
                worker,
                error,
                canonical_json({"checkpoint": checkpoint} if checkpoint else {}),
                now,
            ),
        )


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


__all__ = ["SQLiteLifecycleStoreMixin"]
