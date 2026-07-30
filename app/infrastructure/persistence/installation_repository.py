"""Transactional repository for the final local installation record."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from app.infrastructure.persistence.installation_config_validation import (
    validate_installation_milestone_config,
)
from app.infrastructure.persistence.installation_milestones import (
    complete_installation_milestone,
)
from app.infrastructure.persistence.installation_record import (
    InstallationRecord,
    installation_record_from_row,
    installation_step_states,
)
from app.infrastructure.persistence.installation_storage_cutover import (
    ensure_installation_storage_cutover,
)
from app.infrastructure.persistence.store import get_db


class InstallationRepository:
    """Own every runtime access to the final local installation singleton."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._config_path = Path(db_path).resolve().parent / "config.yaml"

    def get_progress(self) -> InstallationRecord:
        """Load progress after atomically cutting over and reconciling an Owner."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            self._reconcile_existing_owner(connection)
            record = self._record(connection)
            connection.commit()
        return record

    def require_current_step(self, step: int) -> None:
        """Fail before external Setup side effects when a step is out of order."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            self._reconcile_existing_owner(connection)
            self._require_current_step(self._record(connection), step)
            connection.commit()

    def complete_step(
        self,
        *,
        step: int,
        decision: str | None,
        model_reference: str | None,
        ollama_endpoint: str | None,
        config_snapshot: Mapping[str, Any] | None,
    ) -> InstallationRecord:
        """Commit one final Setup milestone in wizard order."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            self._reconcile_existing_owner(connection)
            record = self._record(connection)
            if self._step_is_completed(record, step):
                connection.commit()
                return record
            self._require_current_step(record, step)
            validate_installation_milestone_config(
                self._config_path,
                config_snapshot=config_snapshot,
                step=step,
                decision=decision,
                ollama_endpoint=ollama_endpoint,
                model_reference=model_reference,
            )
            complete_installation_milestone(
                connection,
                record,
                step=step,
                decision=decision,
                model_reference=model_reference,
                ollama_endpoint=ollama_endpoint,
            )
            updated = self._record(connection)
            connection.commit()
        return updated

    def record_task_failure(
        self,
        *,
        step: int,
        task_key: str,
        error_message: str,
    ) -> None:
        """Persist one retryable task failure without changing prior milestones."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            self._reconcile_existing_owner(connection)
            self._require_current_step(self._record(connection), step)
            connection.execute(
                """
                UPDATE local_installations
                SET setup_state = 'in_progress', active_task_step = ?,
                    active_task_key = ?, task_state = 'failed', task_progress = 0,
                    last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE installation_id = 'local'
                """,
                (step, task_key, error_message),
            )
            connection.commit()

    def begin_task(self, *, step: int, task_key: str) -> InstallationRecord:
        """Atomically reserve the singleton task slot."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            self._reconcile_existing_owner(connection)
            record = self._record(connection)
            self._require_current_step(record, step)
            if record.task_state == "running":
                raise RuntimeError("当前 Setup 步骤已有进行中的任务")
            connection.execute(
                """
                UPDATE local_installations
                SET setup_state = 'in_progress', active_task_step = ?,
                    active_task_key = ?, task_state = 'running', task_progress = 1,
                    last_error = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE installation_id = 'local'
                """,
                (step, task_key),
            )
            updated = self._record(connection)
            connection.commit()
        return updated

    def update_task_progress(self, *, step: int, task_key: str, progress: int) -> None:
        """Advance only the matching running task."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            cursor = connection.execute(
                """
                UPDATE local_installations
                SET task_progress = ?, updated_at = CURRENT_TIMESTAMP
                WHERE installation_id = 'local' AND active_task_step = ?
                  AND active_task_key = ? AND task_state = 'running'
                """,
                (progress, step, task_key),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Setup 任务不再处于运行状态")
            connection.commit()

    def cancel_task(self, *, step: int, task_key: str) -> None:
        """Cancel only the matching running task."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            cursor = connection.execute(
                """
                UPDATE local_installations
                SET task_state = 'cancelled', task_progress = 0,
                    last_error = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE installation_id = 'local' AND active_task_step = ?
                  AND active_task_key = ? AND task_state = 'running'
                """,
                (step, task_key),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("没有可取消的 Setup 任务")
            connection.commit()

    def get_task(self) -> InstallationRecord:
        """Load the singleton without changing milestone state."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            record = self._record(connection)
            connection.commit()
        return record

    def recover_interrupted_task(self, *, error_message: str) -> None:
        """Convert a process-local running task into a retryable failure."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_cutover(connection)
            connection.execute(
                """
                UPDATE local_installations
                SET task_state = 'failed', task_progress = 0,
                    last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE installation_id = 'local' AND task_state = 'running'
                """,
                (error_message,),
            )
            connection.commit()

    def mark_owner_step_completed(
        self,
        connection: sqlite3.Connection,
        user_id: int,
    ) -> None:
        """Advance step one inside the caller's Owner-creation transaction."""
        self._ensure_cutover(connection)
        connection.execute(
            """
            UPDATE local_installations
            SET owner_user_id = ?, setup_state = 'in_progress',
                setup_step = CASE
                    WHEN setup_step = 'not_started' THEN 'owner' ELSE setup_step END,
                owner_completed_at = COALESCE(owner_completed_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE installation_id = 'local'
            """,
            (user_id,),
        )

    def _ensure_cutover(self, connection: sqlite3.Connection) -> None:
        ensure_installation_storage_cutover(
            connection,
            config_path=self._config_path,
        )

    def _reconcile_existing_owner(self, connection: sqlite3.Connection) -> None:
        owner = connection.execute(
            "SELECT id FROM users WHERE role = 'owner' ORDER BY id LIMIT 1"
        ).fetchone()
        if owner is not None:
            self.mark_owner_step_completed(connection, int(owner[0]))

    @staticmethod
    def _record(connection: sqlite3.Connection) -> InstallationRecord:
        row = connection.execute(
            """
            SELECT owner_user_id, setup_state, setup_step, active_task_step,
                   active_task_key, task_state, task_progress, last_error, completed_at
            FROM local_installations WHERE installation_id = 'local'
            """
        ).fetchone()
        if row is None:
            raise RuntimeError("Setup 安装记录缺失")
        return installation_record_from_row(row)

    @staticmethod
    def _step_is_completed(record: InstallationRecord, step: int) -> bool:
        if step not in range(1, 6):
            raise ValueError("未知 Setup 步骤")
        return installation_step_states(record)[step - 1]

    @staticmethod
    def _require_current_step(record: InstallationRecord, step: int) -> None:
        states = installation_step_states(record)
        current = next(
            (number for number, complete in enumerate(states, start=1) if not complete),
            5,
        )
        if step != current:
            raise ValueError(f"请先完成第 {current} 步")
