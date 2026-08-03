"""Persistence boundary for the single resumable first-run Setup draft."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass

from app.features.setup.model_catalog import get_setup_model
from app.infrastructure.persistence.store import get_db


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


class SetupDraftRepository:
    """Own all SQL for the one-row ``setup_drafts`` table."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def get(self) -> SetupDraftRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self._record(connection)
            connection.commit()
        return record

    def save_owner(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str | None,
    ) -> SetupDraftRecord:
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
            connection.execute(
                """UPDATE setup_drafts SET owner_account_id=?,display_name=?,
                   password_hash=COALESCE(?,password_hash),owner_configured=1,
                   updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
                (normalized_account_id, normalized_display_name, password_hash),
            )
            record = self._record(connection)
            connection.commit()
        return record

    def save_offline(
        self, *, use_local_ollama: bool, model_id: str | None
    ) -> SetupDraftRecord:
        normalized_model_id = model_id if use_local_ollama else None
        if use_local_ollama:
            if normalized_model_id is None:
                raise ValueError("启用本地 Ollama 时必须选择模型")
            get_setup_model(normalized_model_id)
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            connection.execute(
                """UPDATE setup_drafts SET use_local_ollama=?,model_id=?,
                   offline_configured=1,updated_at=CURRENT_TIMESTAMP
                   WHERE installation_id='local'""",
                (int(use_local_ollama), normalized_model_id),
            )
            record = self._record(connection)
            connection.commit()
        return record

    def save_nest(self, *, bed_count: int) -> SetupDraftRecord:
        if bed_count < 4 or bed_count > 32:
            raise ValueError("床位数必须在 4 到 32 之间")
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            connection.execute(
                """UPDATE setup_drafts SET bed_count=?,nest_configured=1,
                   updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'""",
                (bed_count,),
            )
            record = self._record(connection)
            connection.commit()
        return record

    def lock(self) -> bool:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self._record(connection)
            if record.locked_at is not None:
                connection.commit()
                return False
            if not record.complete or record.password_hash is None:
                raise ValueError("Setup 配置尚未完成")
            connection.execute(
                """UPDATE setup_drafts SET locked_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP WHERE installation_id='local'"""
            )
            connection.commit()
        return True

    @staticmethod
    def _ensure_row(connection: sqlite3.Connection) -> None:
        connection.execute(
            """INSERT OR IGNORE INTO local_installations
               (installation_id,device_name,platform) VALUES ('local','local',?)""",
            (sys.platform,),
        )
        connection.execute(
            "INSERT OR IGNORE INTO setup_drafts (installation_id) VALUES ('local')"
        )

    @staticmethod
    def _record(connection: sqlite3.Connection) -> SetupDraftRecord:
        row = connection.execute(
            """SELECT owner_account_id,display_name,password_hash,use_local_ollama,
                      model_id,bed_count,owner_configured,offline_configured,
                      nest_configured,locked_at FROM setup_drafts
                      WHERE installation_id='local'"""
        ).fetchone()
        if row is None:
            raise RuntimeError("Setup 草稿记录缺失")
        return SetupDraftRecord(
            owner_account_id=None if row[0] is None else str(row[0]),
            display_name=None if row[1] is None else str(row[1]),
            password_hash=None if row[2] is None else str(row[2]),
            use_local_ollama=None if row[3] is None else bool(row[3]),
            model_id=None if row[4] is None else str(row[4]),
            bed_count=None if row[5] is None else int(row[5]),
            owner_configured=bool(row[6]),
            offline_configured=bool(row[7]),
            nest_configured=bool(row[8]),
            locked_at=None if row[9] is None else str(row[9]),
        )


__all__ = ("SetupDraftRecord", "SetupDraftRepository")
