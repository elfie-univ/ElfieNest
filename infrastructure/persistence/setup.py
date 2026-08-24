"""SQLite Adapter for the one first-run Setup state and account seed."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Callable, Literal, Mapping, Optional, cast

from app.features.setup import (
    SetupPortError,
    StoredSetupDraft,
    StoredSetupInstallation,
)
from app.orchestration.setup_installation import (
    SetupInstallationConflict,
    SetupInstallationPortError,
)
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection


class SQLiteSetupAdapter:
    """Use the existing ``local_installations`` row as the sole Setup fact."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def read_installation(self) -> StoredSetupInstallation:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    """SELECT owner_user_id,status,install_step,install_action,
                              task_status,task_progress,last_error,setup_completed_at
                       FROM local_installations WHERE installation_id='local'"""
                ).fetchone()
            return _default_installation() if row is None else _installation(row)
        except (sqlite3.DatabaseError, ValueError) as error:
            raise SetupPortError("unable to read Setup installation") from error

    def read_draft(self) -> StoredSetupDraft:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    "SELECT setup_draft_json FROM local_installations WHERE installation_id='local'"
                ).fetchone()
            return (
                _default_draft()
                if row is None or row[0] is None
                else _draft(str(row[0]))
            )
        except (
            sqlite3.DatabaseError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise SetupPortError("unable to read Setup draft") from error

    def save_owner_draft(
        self,
        *,
        account_id: str,
        display_name: Optional[str],
        password_hash: Optional[str],
    ) -> StoredSetupDraft:
        def update(values: dict[str, object]) -> None:
            values["owner_account_id"] = account_id.strip()
            values["display_name"] = (
                display_name.strip() if display_name and display_name.strip() else None
            )
            if password_hash is not None:
                values["password_hash"] = password_hash
            values["owner_configured"] = True

        return self._update_draft(update)

    def save_offline_draft(
        self, *, use_local_ollama: bool, model_id: Optional[str]
    ) -> StoredSetupDraft:
        def update(values: dict[str, object]) -> None:
            values["use_local_ollama"] = use_local_ollama
            values["model_id"] = model_id if use_local_ollama else None
            values["offline_configured"] = True

        return self._update_draft(update)

    def save_nest_draft(self, *, bed_count: int) -> StoredSetupDraft:
        def update(values: dict[str, object]) -> None:
            values["bed_count"] = bed_count
            values["nest_configured"] = True

        return self._update_draft(update)

    def lock_draft(self) -> StoredSetupDraft:
        def update(values: dict[str, object]) -> None:
            draft = _draft_from_mapping(values)
            if not draft.complete or draft.password_hash is None:
                raise SetupInstallationConflict("Setup 配置尚未完成")
            if draft.locked_at is None:
                values["locked_at"] = datetime.now(timezone.utc).isoformat()

        try:
            return self._update_draft(update)
        except SetupPortError as error:
            raise SetupInstallationPortError(str(error)) from error

    def mark_owner_completed(self, user_id: int) -> None:
        self._mutate(
            """UPDATE local_installations SET owner_user_id=?,
               status=CASE WHEN status='completed' THEN status ELSE 'in_progress' END,
               updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
            (user_id,),
        )

    def begin_or_resume(self) -> StoredSetupInstallation:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._ensure_row(connection)
                row = self._read_installation_row(connection)
                current = _installation(row)
                if current.task_status in {"running", "completed"}:
                    connection.commit()
                    return current
                phase = min(max(current.install_step or 2, 2), 5)
                progress = max(
                    current.task_progress, {2: 20, 3: 40, 4: 60, 5: 80}[phase]
                )
                connection.execute(
                    """UPDATE local_installations SET status='in_progress',install_step=?,
                       install_action='pending',task_status='running',task_progress=?,
                       last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
                    (phase, progress),
                )
                result = _installation(self._read_installation_row(connection))
                connection.commit()
                return result
        except sqlite3.DatabaseError as error:
            raise SetupInstallationPortError(
                "unable to start Setup installation"
            ) from error

    def report(self, *, phase: int, action_key: str, progress: int) -> None:
        self._mutate(
            """UPDATE local_installations SET install_step=?,install_action=?,task_status='running',
               task_progress=?,last_error=NULL,updated_at=CURRENT_TIMESTAMP
               WHERE installation_id='local' AND task_status='running' AND install_step=?""",
            (phase, action_key, progress, phase),
            require_row=True,
        )

    def complete_phase(self, phase: int) -> StoredSetupInstallation:
        if phase not in range(2, 6):
            raise SetupInstallationPortError("invalid Setup phase")
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if phase == 5:
                    cursor = connection.execute(
                        """UPDATE local_installations SET status='completed',install_step=5,
                           install_action='complete',task_status='completed',task_progress=100,
                           last_error=NULL,setup_completed_at=COALESCE(setup_completed_at,CURRENT_TIMESTAMP),
                           updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'
                           AND task_status='running' AND install_step=5"""
                    )
                else:
                    cursor = connection.execute(
                        """UPDATE local_installations SET install_step=?,install_action='pending',
                           task_progress=?,updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'
                           AND task_status='running' AND install_step=?""",
                        (phase + 1, {2: 40, 3: 60, 4: 80}[phase], phase),
                    )
                if cursor.rowcount != 1:
                    raise SetupInstallationPortError("Setup phase no longer running")
                result = _installation(self._read_installation_row(connection))
                connection.commit()
                return result
        except SetupInstallationPortError:
            raise
        except sqlite3.DatabaseError as error:
            raise SetupInstallationPortError(
                "unable to complete Setup phase"
            ) from error

    def fail(self, action_key: str, error: str) -> None:
        self._finish_running(
            task_status="failed",
            action_key=action_key or "unknown",
            error=error[:512],
        )

    def cancel_installation(self) -> StoredSetupInstallation:
        return self._finish_running(
            task_status="cancelled",
            action_key="cancelled",
            error=None,
        )

    def recover_running(self, error: str) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """SELECT task_status,setup_draft_json FROM local_installations
                       WHERE installation_id='local'"""
                ).fetchone()
                if row is None or str(row[0]) not in {
                    "running",
                    "failed",
                    "cancelled",
                }:
                    connection.commit()
                    return
                unlocked_draft = _unlocked_draft_json(row[1])
                if str(row[0]) == "running":
                    connection.execute(
                        """UPDATE local_installations SET task_status='failed',last_error=?,
                           setup_draft_json=?,updated_at=CURRENT_TIMESTAMP
                           WHERE installation_id='local' AND task_status='running'""",
                        (error[:512], unlocked_draft),
                    )
                else:
                    connection.execute(
                        """UPDATE local_installations SET setup_draft_json=?,
                           updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
                        (unlocked_draft,),
                    )
                connection.commit()
        except (
            sqlite3.DatabaseError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as cause:
            raise SetupInstallationPortError(
                "unable to recover Setup installation"
            ) from cause

    def _finish_running(
        self,
        *,
        task_status: Literal["failed", "cancelled"],
        action_key: str,
        error: Optional[str],
    ) -> StoredSetupInstallation:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """SELECT setup_draft_json FROM local_installations
                       WHERE installation_id='local' AND task_status='running'"""
                ).fetchone()
                if row is None:
                    raise SetupInstallationPortError("Setup task no longer running")
                cursor = connection.execute(
                    """UPDATE local_installations SET install_action=?,task_status=?,last_error=?,
                       setup_draft_json=?,updated_at=CURRENT_TIMESTAMP
                       WHERE installation_id='local' AND task_status='running'""",
                    (
                        action_key,
                        task_status,
                        error,
                        _unlocked_draft_json(row[0]),
                    ),
                )
                if cursor.rowcount != 1:
                    raise SetupInstallationPortError("Setup task no longer running")
                result = _installation(self._read_installation_row(connection))
                connection.commit()
                return result
        except SetupInstallationPortError:
            raise
        except (
            sqlite3.DatabaseError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as cause:
            raise SetupInstallationPortError(
                "unable to finish Setup installation"
            ) from cause

    def _update_draft(
        self, update: Callable[[dict[str, object]], None]
    ) -> StoredSetupDraft:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._ensure_row(connection)
                current = connection.execute(
                    "SELECT setup_draft_json FROM local_installations WHERE installation_id='local'"
                ).fetchone()
                values = (
                    _default_draft_mapping()
                    if current is None or current[0] is None
                    else cast(dict[str, object], json.loads(str(current[0])))
                )
                update(values)
                connection.execute(
                    "UPDATE local_installations SET setup_draft_json=?,updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'",
                    (json.dumps(values, ensure_ascii=False),),
                )
                connection.commit()
                return _draft_from_mapping(values)
        except SetupInstallationConflict:
            raise
        except (
            sqlite3.DatabaseError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise SetupPortError("unable to update Setup draft") from error

    def _mutate(
        self,
        sql: str,
        parameters: tuple[object, ...],
        *,
        require_row: bool = False,
        ensure_row: bool = True,
    ) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if ensure_row:
                    self._ensure_row(connection)
                cursor = connection.execute(sql, parameters)
                if require_row and cursor.rowcount != 1:
                    raise SetupInstallationPortError("Setup task no longer running")
                connection.commit()
        except SetupInstallationPortError:
            raise
        except sqlite3.DatabaseError as error:
            raise SetupInstallationPortError(
                "unable to update Setup installation"
            ) from error

    @staticmethod
    def _ensure_row(connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO local_installations (installation_id,device_name,platform) VALUES ('local','local',?)",
            (sys.platform,),
        )

    @staticmethod
    def _read_installation_row(connection: sqlite3.Connection) -> sqlite3.Row:
        row = connection.execute(
            """SELECT owner_user_id,status,install_step,install_action,task_status,
                      task_progress,last_error,setup_completed_at FROM local_installations
               WHERE installation_id='local'"""
        ).fetchone()
        if row is None:
            raise SetupInstallationPortError("Setup installation row missing")
        return cast(sqlite3.Row, row)


def _default_draft_mapping() -> dict[str, object]:
    return {
        "owner_account_id": None,
        "display_name": None,
        "password_hash": None,
        "use_local_ollama": None,
        "model_id": None,
        "bed_count": None,
        "owner_configured": False,
        "offline_configured": False,
        "nest_configured": False,
        "locked_at": None,
    }


def _default_draft() -> StoredSetupDraft:
    return _draft_from_mapping(_default_draft_mapping())


def _draft(raw: str) -> StoredSetupDraft:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Setup draft is not an object")
    return _draft_from_mapping(cast(Mapping[str, object], value))


def _draft_from_mapping(value: Mapping[str, object]) -> StoredSetupDraft:
    return StoredSetupDraft(
        owner_account_id=_text(value.get("owner_account_id")),
        display_name=_text(value.get("display_name")),
        password_hash=_text(value.get("password_hash")),
        use_local_ollama=_boolean(value.get("use_local_ollama")),
        model_id=_text(value.get("model_id")),
        bed_count=_integer(value.get("bed_count")),
        owner_configured=value.get("owner_configured") is True,
        offline_configured=value.get("offline_configured") is True,
        nest_configured=value.get("nest_configured") is True,
        locked_at=_text(value.get("locked_at")),
    )


def _default_installation() -> StoredSetupInstallation:
    return StoredSetupInstallation(
        None, "not_started", None, None, "idle", 0, None, None
    )


def _installation(row: sqlite3.Row) -> StoredSetupInstallation:
    task = str(row[4])
    if task not in {"idle", "running", "failed", "completed", "cancelled"}:
        task = "idle"
    return StoredSetupInstallation(
        None if row[0] is None else int(row[0]),
        str(row[1]),
        None if row[2] is None else int(row[2]),
        None if row[3] is None else str(row[3]),
        cast(Literal["idle", "running", "failed", "completed", "cancelled"], task),
        int(row[5]),
        None if row[6] is None else str(row[6]),
        None if row[7] is None else str(row[7]),
    )


def _text(value: object) -> Optional[str]:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("invalid Setup text")


def _boolean(value: object) -> Optional[bool]:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError("invalid Setup boolean")


def _integer(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid Setup integer")
    return value


def _unlocked_draft_json(raw: object) -> str:
    values = (
        _default_draft_mapping()
        if raw is None
        else cast(dict[str, object], json.loads(str(raw)))
    )
    values["locked_at"] = None
    return json.dumps(values, ensure_ascii=False)


__all__ = ("SQLiteSetupAdapter",)
