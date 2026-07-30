"""Transactional access to the final local installation singleton."""

from __future__ import annotations

import sqlite3
import sys
from typing import NamedTuple

from app.infrastructure.persistence.store import get_db


class InstallationRecord(NamedTuple):
    owner_user_id: int | None
    setup_state: str
    setup_step: str
    active_task_step: int | None
    active_task_key: str | None
    task_state: str
    task_progress: int
    last_error: str | None
    completed_at: str | None


class InstallationRepository:
    """Own every runtime access to ``local_installations``."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def get_progress(self) -> InstallationRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            self._reconcile_owner(connection)
            record = self._record(connection)
            connection.commit()
        return record

    def complete_step(self, step: int) -> InstallationRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            self._reconcile_owner(connection)
            record = self._record(connection)
            if _step_completed(record, step):
                connection.commit()
                return record
            _require_current_step(record, step)
            setup_step, setup_state, milestone = _completion_update(step)
            connection.execute(
                f"""UPDATE local_installations
                    SET setup_step=?,setup_state=?,{milestone}=COALESCE({milestone},CURRENT_TIMESTAMP),
                        active_task_step=NULL,active_task_key=NULL,task_state='completed',
                        task_progress=100,last_error=NULL,updated_at=CURRENT_TIMESTAMP
                    WHERE installation_id='local'""",
                (setup_step, setup_state),
            )
            updated = self._record(connection)
            connection.commit()
        return updated

    def record_task_failure(self, step: int, task_key: str, error: str) -> None:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            self._reconcile_owner(connection)
            _require_current_step(self._record(connection), step)
            connection.execute(
                """UPDATE local_installations SET setup_state='in_progress',
                   active_task_step=?,active_task_key=?,task_state='failed',task_progress=0,
                   last_error=?,updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
                (step, task_key, error),
            )
            connection.commit()

    def begin_task(self, step: int, task_key: str) -> InstallationRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            self._reconcile_owner(connection)
            record = self._record(connection)
            _require_current_step(record, step)
            if record.task_state == "running":
                raise RuntimeError("当前 Setup 步骤已有进行中的任务")
            connection.execute(
                """UPDATE local_installations SET setup_state='in_progress',
                   active_task_step=?,active_task_key=?,task_state='running',task_progress=1,
                   last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
                (step, task_key),
            )
            updated = self._record(connection)
            connection.commit()
        return updated

    def update_task_progress(self, step: int, task_key: str, progress: int) -> None:
        self._update_matching_task(
            step,
            task_key,
            "task_progress=?,updated_at=CURRENT_TIMESTAMP",
            (progress,),
            "Setup 任务不再处于运行状态",
        )

    def cancel_task(self, step: int, task_key: str) -> None:
        self._update_matching_task(
            step,
            task_key,
            "task_state='cancelled',task_progress=0,last_error=NULL,updated_at=CURRENT_TIMESTAMP",
            (),
            "没有可取消的 Setup 任务",
        )

    def recover_interrupted_task(self, error: str) -> None:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            connection.execute(
                """UPDATE local_installations SET task_state='failed',task_progress=0,
                   last_error=?,updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local' AND task_state='running'""",
                (error,),
            )
            connection.commit()

    def mark_owner_completed(
        self, connection: sqlite3.Connection, user_id: int
    ) -> None:
        self._ensure_record(connection)
        connection.execute(
            """UPDATE local_installations SET owner_user_id=?,
               setup_state=CASE WHEN setup_state='completed' THEN setup_state ELSE 'in_progress' END,
               setup_step=CASE WHEN setup_step='not_started' THEN 'owner' ELSE setup_step END,
               owner_completed_at=COALESCE(owner_completed_at,CURRENT_TIMESTAMP),
               updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
            (user_id,),
        )

    def _update_matching_task(
        self,
        step: int,
        task_key: str,
        assignment: str,
        values: tuple[int, ...],
        error: str,
    ) -> None:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            cursor = connection.execute(
                f"""UPDATE local_installations SET {assignment}
                    WHERE installation_id='local' AND active_task_step=?
                      AND active_task_key=? AND task_state='running'""",
                values + (step, task_key),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(error)
            connection.commit()

    @staticmethod
    def _ensure_record(connection: sqlite3.Connection) -> None:
        connection.execute(
            """INSERT OR IGNORE INTO local_installations
               (installation_id,device_name,platform) VALUES ('local','local',?)""",
            (sys.platform,),
        )

    def _reconcile_owner(self, connection: sqlite3.Connection) -> None:
        owner = connection.execute(
            "SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1"
        ).fetchone()
        if owner is not None:
            self.mark_owner_completed(connection, int(owner[0]))

    @staticmethod
    def _record(connection: sqlite3.Connection) -> InstallationRecord:
        row = connection.execute(
            """SELECT owner_user_id,setup_state,setup_step,active_task_step,
                      active_task_key,task_state,task_progress,last_error,completed_at
               FROM local_installations WHERE installation_id='local'"""
        ).fetchone()
        if row is None:
            raise RuntimeError("Setup 安装记录缺失")
        return InstallationRecord(
            owner_user_id=None if row[0] is None else int(row[0]),
            setup_state=str(row[1]),
            setup_step=str(row[2]),
            active_task_step=None if row[3] is None else int(row[3]),
            active_task_key=None if row[4] is None else str(row[4]),
            task_state=str(row[5]),
            task_progress=int(row[6]),
            last_error=None if row[7] is None else str(row[7]),
            completed_at=None if row[8] is None else str(row[8]),
        )


def _completed_count(record: InstallationRecord) -> int:
    if record.setup_state == "completed":
        return 5
    return ("not_started", "owner", "providers", "nest", "food").index(
        record.setup_step
    )


def _step_completed(record: InstallationRecord, step: int) -> bool:
    if step not in range(1, 6):
        raise ValueError("未知 Setup 步骤")
    return step <= _completed_count(record)


def _require_current_step(record: InstallationRecord, step: int) -> None:
    current = min(_completed_count(record) + 1, 5)
    if step != current:
        raise ValueError(f"请先完成第 {current} 步")


def _completion_update(step: int) -> tuple[str, str, str]:
    updates = {
        2: ("providers", "in_progress", "providers_completed_at"),
        3: ("nest", "in_progress", "nest_completed_at"),
        4: ("food", "in_progress", "food_completed_at"),
        5: ("food", "completed", "completed_at"),
    }
    try:
        return updates[step]
    except KeyError as error:
        raise ValueError("只能通过 Owner 创建完成第一步") from error
