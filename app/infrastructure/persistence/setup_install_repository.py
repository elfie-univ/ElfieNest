"""Canonical persistence boundary for Setup installation and its draft."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass

from app.infrastructure.persistence.setup_install_draft import (
    SetupDraftRecord,
    SetupInstallDraftStore,
)
from app.infrastructure.persistence.setup_install_errors import sanitize_setup_error
from app.infrastructure.persistence.store import get_db


@dataclass(frozen=True)
class SetupInstallRecord:
    owner_user_id: int | None
    status: str
    setup_step: str
    install_step: int | None
    install_action: str | None
    task_status: str
    task_progress: int
    last_error: str | None
    setup_completed_at: str | None


class SetupInstallRepository:
    """Own the complete Setup installation persistence interface."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._drafts = SetupInstallDraftStore(db_path, self._ensure_row)

    def get(self) -> SetupInstallRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            self._reconcile_owner(connection)
            record = self._record(connection)
            connection.commit()
        return record

    def begin_or_resume(self) -> SetupInstallRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            self._reconcile_owner(connection)
            record = self._record(connection)
            if record.status == "completed" or record.task_status == "running":
                connection.commit()
                return record
            phase = min(max(record.install_step or 2, 2), 5)
            progress = max(record.task_progress, _phase_start_progress(phase))
            connection.execute(
                """UPDATE local_installations SET status='in_progress',
                   install_step=?,install_action='pending',task_status='running',
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
            record = self._record(connection)
            if record.task_status != "running":
                raise RuntimeError("Setup 安装任务不再运行")
            if record.install_step != phase:
                raise RuntimeError("Setup 当前安装阶段不匹配")
            cursor = connection.execute(
                """UPDATE local_installations SET install_step=?,install_action=?,
                   task_status='running',task_progress=?,last_error=NULL,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local' AND task_status='running'""",
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
            if record.task_status != "running":
                raise RuntimeError("Setup 安装任务不再运行")
            if record.install_step != phase:
                raise RuntimeError("Setup 当前安装阶段不匹配")
            if phase == 5:
                connection.execute(
                    """UPDATE local_installations SET status='completed',
                       install_step=5,install_action='complete',task_status='completed',
                       task_progress=100,last_error=NULL,
                       setup_completed_at=COALESCE(setup_completed_at,CURRENT_TIMESTAMP),
                       updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'"""
                )
            else:
                next_phase = phase + 1
                connection.execute(
                    """UPDATE local_installations SET install_step=?,
                       install_action='pending',task_progress=?,updated_at=CURRENT_TIMESTAMP
                       WHERE installation_id='local'""",
                    (next_phase, _phase_end_progress(phase)),
                )
            updated = self._record(connection)
            connection.commit()
        return updated

    def fail(self, action_key: str, error: str) -> None:
        safe_error = sanitize_setup_error(error, "Setup 安装失败")
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            cursor = connection.execute(
                """UPDATE local_installations SET install_action=?,task_status='failed',
                   last_error=?,updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local' AND task_status='running'""",
                (action_key.strip() or "unknown", safe_error),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Setup 安装任务不再运行")
            connection.commit()

    def recover_running(self, error: str) -> None:
        safe_error = sanitize_setup_error(error, "Setup 安装任务中断")
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            connection.execute(
                """UPDATE local_installations SET task_status='failed',last_error=?,
                   updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'
                   AND task_status='running'""",
                (safe_error,),
            )
            connection.commit()

    def mark_owner_completed(
        self, connection: sqlite3.Connection, user_id: int
    ) -> None:
        self._ensure_row(connection)
        connection.execute(
            """UPDATE local_installations SET owner_user_id=?,
               status=CASE WHEN status='completed' THEN status ELSE 'in_progress' END,
               updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
            (user_id,),
        )

    def get_draft(self) -> SetupDraftRecord:
        return self._drafts.get()

    def save_owner_draft(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str | None,
    ) -> SetupDraftRecord:
        return self._drafts.save_owner(
            account_id=account_id,
            display_name=display_name,
            password_hash=password_hash,
        )

    def save_offline_draft(
        self, *, use_local_ollama: bool, model_id: str | None
    ) -> SetupDraftRecord:
        return self._drafts.save_offline(
            use_local_ollama=use_local_ollama, model_id=model_id
        )

    def save_nest_draft(self, *, bed_count: int) -> SetupDraftRecord:
        return self._drafts.save_nest(bed_count=bed_count)

    def lock_draft(self) -> bool:
        return self._drafts.lock()

    @staticmethod
    def _ensure_row(connection: sqlite3.Connection) -> None:
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

    def _record(self, connection: sqlite3.Connection) -> SetupInstallRecord:
        row = connection.execute(
            """SELECT owner_user_id,status,install_step,install_action,
                      task_status,task_progress,last_error,setup_completed_at
               FROM local_installations
                      WHERE installation_id='local'"""
        ).fetchone()
        if row is None:
            raise RuntimeError("Setup 安装记录缺失")
        owner_user_id = None if row[0] is None else int(row[0])
        install_step = None if row[2] is None else int(row[2])
        draft = self._drafts.record_for_transaction(connection)
        owner_complete = owner_user_id is not None or draft.owner_configured
        if install_step is not None and install_step >= 4:
            setup_step = "food"
        elif not owner_complete:
            setup_step = "not_started"
        elif not draft.offline_configured:
            setup_step = "owner"
        elif not draft.nest_configured:
            setup_step = "providers"
        else:
            setup_step = "nest"
        return SetupInstallRecord(
            owner_user_id=owner_user_id,
            status=str(row[1]),
            setup_step=setup_step,
            install_step=install_step,
            install_action=None if row[3] is None else str(row[3]),
            task_status=str(row[4]),
            task_progress=int(row[5]),
            last_error=None if row[6] is None else str(row[6]),
            setup_completed_at=None if row[7] is None else str(row[7]),
        )

def _validate_phase(phase: int) -> None:
    if phase not in range(2, 6):
        raise ValueError("Setup 安装阶段必须为 2 到 5")


def _phase_start_progress(phase: int) -> int:
    return {2: 20, 3: 40, 4: 60, 5: 80}[phase]


def _phase_end_progress(phase: int) -> int:
    return {2: 40, 3: 60, 4: 80, 5: 100}[phase]


__all__ = (
    "SetupDraftRecord",
    "SetupInstallRecord",
    "SetupInstallRepository",
)
