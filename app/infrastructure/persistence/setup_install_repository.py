"""Persistence boundary for the locked, five-phase Setup installation task."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass

from app.infrastructure.persistence.store import get_db


@dataclass(frozen=True)
class SetupInstallRecord:
    setup_state: str
    active_task_step: int | None
    active_task_key: str | None
    task_state: str
    task_progress: int
    last_error: str | None
    completed_at: str | None


class SetupInstallRepository:
    """Own the install task projection without changing the old Setup API."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def get(self) -> SetupInstallRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self._record(connection)
            connection.commit()
        return record

    def begin_or_resume(self) -> SetupInstallRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self._record(connection)
            if record.setup_state == "completed" or record.task_state == "running":
                connection.commit()
                return record
            phase = record.active_task_step or 2
            phase = min(max(phase, 2), 5)
            progress = max(record.task_progress, _phase_start_progress(phase))
            connection.execute(
                """UPDATE local_installations SET setup_state='in_progress',
                   active_task_step=?,active_task_key='pending',task_state='running',
                   task_progress=?,last_error=NULL,updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local'""",
                (phase, progress),
            )
            updated = self._record(connection)
            connection.commit()
        return updated

    def update(self, *, phase: int, action_key: str, progress: int) -> None:
        _validate_phase(phase)
        if not 0 <= progress <= 100:
            raise ValueError("Setup 总进度必须在 0 到 100 之间")
        if not action_key.strip():
            raise ValueError("Setup 动作不能为空")
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            cursor = connection.execute(
                """UPDATE local_installations SET active_task_step=?,active_task_key=?,
                   task_state='running',task_progress=?,last_error=NULL,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local' AND task_state='running'""",
                (phase, action_key.strip(), progress),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Setup 安装任务不再运行")
            connection.commit()

    def complete_phase(self, *, phase: int) -> SetupInstallRecord:
        _validate_phase(phase)
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self._record(connection)
            if record.task_state != "running":
                raise RuntimeError("Setup 安装任务不再运行")
            if phase == 5:
                connection.execute(
                    """UPDATE local_installations SET setup_state='completed',
                       setup_step='food',active_task_step=5,active_task_key='complete',
                       task_state='completed',task_progress=100,last_error=NULL,
                       completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP),
                       updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'"""
                )
            else:
                next_phase = phase + 1
                connection.execute(
                    """UPDATE local_installations SET active_task_step=?,
                       active_task_key='pending',task_progress=?,updated_at=CURRENT_TIMESTAMP
                       WHERE installation_id='local'""",
                    (next_phase, _phase_end_progress(phase)),
                )
            updated = self._record(connection)
            connection.commit()
        return updated

    def fail(self, action_key: str, error: str) -> None:
        safe_error = error.strip()[:512] or "Setup 安装失败"
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            cursor = connection.execute(
                """UPDATE local_installations SET active_task_key=?,task_state='failed',
                   last_error=?,updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local' AND task_state='running'""",
                (action_key.strip() or "unknown", safe_error),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Setup 安装任务不再运行")
            connection.commit()

    def recover_running(self, error: str) -> None:
        safe_error = error.strip()[:512] or "Setup 安装任务中断"
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            connection.execute(
                """UPDATE local_installations SET task_state='failed',last_error=?,
                   updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'
                   AND task_state='running'""",
                (safe_error,),
            )
            connection.commit()

    @staticmethod
    def _ensure_row(connection: sqlite3.Connection) -> None:
        connection.execute(
            """INSERT OR IGNORE INTO local_installations
               (installation_id,device_name,platform) VALUES ('local','local',?)""",
            (sys.platform,),
        )

    @staticmethod
    def _record(connection: sqlite3.Connection) -> SetupInstallRecord:
        row = connection.execute(
            """SELECT setup_state,active_task_step,active_task_key,task_state,
                      task_progress,last_error,completed_at FROM local_installations
                      WHERE installation_id='local'"""
        ).fetchone()
        if row is None:
            raise RuntimeError("Setup 安装记录缺失")
        return SetupInstallRecord(
            setup_state=str(row[0]),
            active_task_step=None if row[1] is None else int(row[1]),
            active_task_key=None if row[2] is None else str(row[2]),
            task_state=str(row[3]),
            task_progress=int(row[4]),
            last_error=None if row[5] is None else str(row[5]),
            completed_at=None if row[6] is None else str(row[6]),
        )


def _validate_phase(phase: int) -> None:
    if phase not in range(2, 6):
        raise ValueError("Setup 安装阶段必须为 2 到 5")


def _phase_start_progress(phase: int) -> int:
    return {2: 20, 3: 40, 4: 60, 5: 80}[phase]


def _phase_end_progress(phase: int) -> int:
    return {2: 40, 3: 60, 4: 80, 5: 100}[phase]


__all__ = ("SetupInstallRecord", "SetupInstallRepository")
