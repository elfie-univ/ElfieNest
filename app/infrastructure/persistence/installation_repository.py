"""Transactional access to the final local installation singleton."""

from __future__ import annotations

import sqlite3
import sys
from typing import NamedTuple

from app.infrastructure.persistence.store import get_db


class InstallationRecord(NamedTuple):
    owner_user_id: int | None
    status: str
    setup_step: str
    install_step: int | None
    install_action: str | None
    task_status: str
    task_progress: int
    last_error: str | None
    setup_completed_at: str | None


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
        from app.infrastructure.persistence.setup_install_repository import (
            SetupInstallRepository,
        )

        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            self._reconcile_owner(connection)
            record = self._record(connection)
            if _step_completed(record, step):
                connection.commit()
                return record
            _require_current_step(record, step)

            # Update draft configuration based on completed step
            draft_repo = SetupInstallRepository(self._db_path)
            draft_dict = draft_repo._load_draft(connection)
            if step == 2:
                draft_dict['use_local_ollama'] = False
                draft_dict['model_id'] = None
                draft_dict['offline_configured'] = True
            elif step == 3:
                draft_dict['bed_count'] = 8
                draft_dict['nest_configured'] = True
            elif step == 4:
                pass
            if step in (2, 3):
                draft_repo._save_draft(connection, draft_dict)

            setup_step, setup_state, milestone = _completion_update(step)

            # For step 5 (completion), also set setup_completed_at
            if step == 5:
                connection.execute(
                    """UPDATE local_installations
                        SET status=?,install_step=?,install_action='completed',
                            task_status='completed',
                            task_progress=100,last_error=NULL,
                            setup_completed_at=COALESCE(setup_completed_at,CURRENT_TIMESTAMP),
                            updated_at=CURRENT_TIMESTAMP
                        WHERE installation_id='local'""",
                    (setup_state, step),
                )
            else:
                connection.execute(
                    f"""UPDATE local_installations
                        SET status=?,install_step=?,install_action='completed',
                            task_status='completed',
                            task_progress=100,last_error=NULL,updated_at=CURRENT_TIMESTAMP
                        WHERE installation_id='local'""",
                    (setup_state, step),
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
                """UPDATE local_installations SET status='in_progress',
                   install_step=?,install_action=?,task_status='failed',task_progress=0,
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
            if record.task_status == "running":
                raise RuntimeError("当前 Setup 步骤已有进行中的任务")
            connection.execute(
                """UPDATE local_installations SET status='in_progress',
                   install_step=?,install_action=?,task_status='running',task_progress=1,
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
            "task_status='cancelled',task_progress=0,last_error=NULL,updated_at=CURRENT_TIMESTAMP",
            (),
            "没有可取消的 Setup 任务",
        )

    def recover_interrupted_task(self, error: str) -> None:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_record(connection)
            connection.execute(
                """UPDATE local_installations SET task_status='failed',task_progress=0,
                   last_error=?,updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local' AND task_status='running'""",
                (error,),
            )
            connection.commit()

    def mark_owner_completed(
        self, connection: sqlite3.Connection, user_id: int
    ) -> None:
        self._ensure_record(connection)
        connection.execute(
            """UPDATE local_installations SET owner_user_id=?,
               status=CASE WHEN status='completed' THEN status ELSE 'in_progress' END,
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
                    WHERE installation_id='local' AND install_step=?
                      AND install_action=? AND task_status='running'""",
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

    def _record(self, connection: sqlite3.Connection) -> InstallationRecord:
        from app.infrastructure.persistence.setup_install_repository import (
            SetupInstallRepository,
        )

        row = connection.execute(
            """SELECT owner_user_id,status,install_step,install_action,
                      task_status,task_progress,last_error,setup_completed_at
               FROM local_installations WHERE installation_id='local'"""
        ).fetchone()
        if row is None:
            raise RuntimeError("Setup 安装记录缺失")

        # Adapter: map new schema fields to old field names
        setup_state = str(row[1])
        owner_user_id = None if row[0] is None else int(row[0])
        install_step = None if row[2] is None else int(row[2])

        # Simulate setup_step from draft status, owner_user_id, and install_step
        draft_repo = SetupInstallRepository(self._db_path)
        draft = draft_repo._draft_record(connection)

        # Owner step is complete if owner_user_id exists or draft.owner_configured
        owner_complete = owner_user_id is not None or draft.owner_configured

        # setup_step represents the last completed step
        # Check install_step first for steps 4-5, then check draft for steps 1-3
        if install_step is not None and install_step >= 4:
            setup_step = "food" if install_step == 4 else "food"
        elif not owner_complete:
            setup_step = "not_started"
        elif not draft.offline_configured:
            setup_step = "owner"
        elif not draft.nest_configured:
            setup_step = "providers"
        else:
            setup_step = "nest"

        return InstallationRecord(
            owner_user_id=owner_user_id,
            status=setup_state,
            setup_step=setup_step,
            install_step=install_step,
            install_action=None if row[3] is None else str(row[3]),
            task_status=str(row[4]),
            task_progress=int(row[5]),
            last_error=None if row[6] is None else str(row[6]),
            setup_completed_at=None if row[7] is None else str(row[7]),
        )


def _completed_count(record: InstallationRecord) -> int:
    if record.status == "completed":
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
