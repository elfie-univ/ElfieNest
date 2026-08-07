"""Persistence boundary for the locked, five-phase Setup installation task."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass

from app.infrastructure.persistence.store import get_db


@dataclass(frozen=True)
class SetupInstallRecord:
    status: str
    install_step: int | None
    install_action: str | None
    task_status: str
    task_progress: int
    last_error: str | None
    setup_completed_at: str | None


@dataclass(frozen=True)
class SetupDraftRecord:
    owner_account_id: str | None
    display_name: str | None
    password_hash: str | None
    use_local_ollama: bool | None
    model_id: str | None
    bed_count: int | None
    owner_configured: bool
    offline_configured: bool
    nest_configured: bool
    locked_at: str | None

    @property
    def password_configured(self) -> bool:
        return self.password_hash is not None

    @property
    def complete(self) -> bool:
        return self.owner_configured and self.offline_configured and self.nest_configured


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
            if record.status == "completed" or record.task_status == "running":
                connection.commit()
                return record
            phase = record.install_step or 2
            phase = min(max(phase, 2), 5)
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
            if phase == 5:
                connection.execute(
                    """UPDATE local_installations SET status='completed',
                       install_step=5,install_action='complete',
                       task_status='completed',task_progress=100,last_error=NULL,
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
        safe_error = error.strip()[:512] or "Setup 安装失败"
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
        safe_error = error.strip()[:512] or "Setup 安装任务中断"
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
            """SELECT status,install_step,install_action,task_status,
                      task_progress,last_error,setup_completed_at FROM local_installations
                      WHERE installation_id='local'"""
        ).fetchone()
        if row is None:
            raise RuntimeError("Setup 安装记录缺失")
        return SetupInstallRecord(
            status=str(row[0]),
            install_step=None if row[1] is None else int(row[1]),
            install_action=None if row[2] is None else str(row[2]),
            task_status=str(row[3]),
            task_progress=int(row[4]),
            last_error=None if row[5] is None else str(row[5]),
            setup_completed_at=None if row[6] is None else str(row[6]),
        )

    def get_draft(self) -> SetupDraftRecord:
        """读取安装草稿"""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self._draft_record(connection)
            connection.commit()
        return record

    def save_owner_draft(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str | None,
    ) -> SetupDraftRecord:
        """保存 Owner 草稿"""
        normalized_account_id = account_id.strip()
        normalized_display_name = (
            display_name.strip() if display_name and display_name.strip() else None
        )
        if not normalized_account_id:
            raise ValueError("Setup Owner 账号不能为空")
        if password_hash is not None and not password_hash:
            raise ValueError("Setup Owner 密码哈希不能为空")

        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)

            draft_dict = self._load_draft(connection)
            draft_dict['owner_account_id'] = normalized_account_id
            draft_dict['display_name'] = normalized_display_name
            if password_hash is not None:
                draft_dict['password_hash'] = password_hash
            draft_dict['owner_configured'] = True

            self._save_draft(connection, draft_dict)
            record = self._draft_record(connection)
            connection.commit()
        return record

    def save_offline_draft(
        self, *, use_local_ollama: bool, model_id: str | None
    ) -> SetupDraftRecord:
        """保存离线配置草稿"""
        from app.features.setup.model_catalog import get_setup_model

        normalized_model_id = model_id if use_local_ollama else None
        if use_local_ollama:
            if normalized_model_id is None:
                raise ValueError("启用本地 Ollama 时必须选择模型")
            get_setup_model(normalized_model_id)

        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)

            draft_dict = self._load_draft(connection)
            draft_dict['use_local_ollama'] = use_local_ollama
            draft_dict['model_id'] = normalized_model_id
            draft_dict['offline_configured'] = True

            self._save_draft(connection, draft_dict)
            record = self._draft_record(connection)
            connection.commit()
        return record

    def save_nest_draft(self, *, bed_count: int) -> SetupDraftRecord:
        """保存 Nest 草稿"""
        if bed_count < 4 or bed_count > 32:
            raise ValueError("床位数必须在 4 到 32 之间")

        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)

            draft_dict = self._load_draft(connection)
            draft_dict['bed_count'] = bed_count
            draft_dict['nest_configured'] = True

            self._save_draft(connection, draft_dict)
            record = self._draft_record(connection)
            connection.commit()
        return record

    def lock_draft(self) -> bool:
        """锁定草稿"""
        from datetime import datetime, timezone

        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self._draft_record(connection)
            if record.locked_at is not None:
                connection.commit()
                return False
            if not record.complete or record.password_hash is None:
                raise ValueError("Setup 配置尚未完成")

            draft_dict = self._load_draft(connection)
            draft_dict['locked_at'] = datetime.now(timezone.utc).isoformat()
            self._save_draft(connection, draft_dict)

            connection.commit()
        return True

    def _load_draft(self, connection: sqlite3.Connection) -> dict:
        row = connection.execute(
            """SELECT setup_draft_json FROM local_installations
               WHERE installation_id='local'"""
        ).fetchone()

        if row is None or row[0] is None:
            return {
                'owner_account_id': None,
                'display_name': None,
                'password_hash': None,
                'use_local_ollama': None,
                'model_id': None,
                'bed_count': None,
                'owner_configured': False,
                'offline_configured': False,
                'nest_configured': False,
                'locked_at': None,
            }

        import json
        return json.loads(row[0])

    def _save_draft(self, connection: sqlite3.Connection, draft: dict) -> None:
        import json
        connection.execute(
            """UPDATE local_installations
               SET setup_draft_json=?, updated_at=CURRENT_TIMESTAMP
               WHERE installation_id='local'""",
            (json.dumps(draft, ensure_ascii=False),),
        )

    def _draft_record(self, connection: sqlite3.Connection) -> SetupDraftRecord:
        draft_dict = self._load_draft(connection)
        return SetupDraftRecord(
            owner_account_id=draft_dict.get('owner_account_id'),
            display_name=draft_dict.get('display_name'),
            password_hash=draft_dict.get('password_hash'),
            use_local_ollama=draft_dict.get('use_local_ollama'),
            model_id=draft_dict.get('model_id'),
            bed_count=draft_dict.get('bed_count'),
            owner_configured=draft_dict.get('owner_configured', False),
            offline_configured=draft_dict.get('offline_configured', False),
            nest_configured=draft_dict.get('nest_configured', False),
            locked_at=draft_dict.get('locked_at'),
        )


def _validate_phase(phase: int) -> None:
    if phase not in range(2, 6):
        raise ValueError("Setup 安装阶段必须为 2 到 5")


def _phase_start_progress(phase: int) -> int:
    return {2: 20, 3: 40, 4: 60, 5: 80}[phase]


def _phase_end_progress(phase: int) -> int:
    return {2: 40, 3: 60, 4: 80, 5: 100}[phase]


__all__ = ("SetupInstallRecord", "SetupDraftRecord", "SetupInstallRepository")
