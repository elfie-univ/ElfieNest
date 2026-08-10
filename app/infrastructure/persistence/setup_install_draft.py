"""Draft storage used by the canonical Setup installation repository."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, TypedDict, Union

from app.infrastructure.persistence.store import get_db

EnsureRow = Callable[[sqlite3.Connection], None]
SetupDraftValue = Union[str, int, float, bool, None]


class SetupDraftData(TypedDict):
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
        return (
            self.owner_configured and self.offline_configured and self.nest_configured
        )


class SetupInstallDraftStore:
    """Persist Setup draft JSON without exposing a second application interface."""

    def __init__(self, db_path: str, ensure_row: EnsureRow) -> None:
        self._db_path = db_path
        self._ensure_row = ensure_row

    def get(self) -> SetupDraftRecord:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self.record_for_transaction(connection)
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
            draft = self.load_for_transaction(connection)
            draft["owner_account_id"] = normalized_account_id
            draft["display_name"] = normalized_display_name
            if password_hash is not None:
                draft["password_hash"] = password_hash
            draft["owner_configured"] = True
            self.save_for_transaction(connection, draft)
            record = self.record_for_transaction(connection)
            connection.commit()
        return record

    def save_offline(
        self, *, use_local_ollama: bool, model_id: str | None
    ) -> SetupDraftRecord:
        normalized_model_id = model_id if use_local_ollama else None

        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            draft = self.load_for_transaction(connection)
            draft["use_local_ollama"] = use_local_ollama
            draft["model_id"] = normalized_model_id
            draft["offline_configured"] = True
            self.save_for_transaction(connection, draft)
            record = self.record_for_transaction(connection)
            connection.commit()
        return record

    def save_nest(self, *, bed_count: int) -> SetupDraftRecord:
        if bed_count < 4 or bed_count > 32:
            raise ValueError("床位数必须在 4 到 32 之间")

        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            draft = self.load_for_transaction(connection)
            draft["bed_count"] = bed_count
            draft["nest_configured"] = True
            self.save_for_transaction(connection, draft)
            record = self.record_for_transaction(connection)
            connection.commit()
        return record

    def lock(self) -> bool:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_row(connection)
            record = self.record_for_transaction(connection)
            if record.locked_at is not None:
                connection.commit()
                return False
            if not record.complete or record.password_hash is None:
                raise ValueError("Setup 配置尚未完成")

            draft = self.load_for_transaction(connection)
            draft["locked_at"] = datetime.now(timezone.utc).isoformat()
            self.save_for_transaction(connection, draft)
            connection.commit()
        return True

    def load_for_transaction(self, connection: sqlite3.Connection) -> SetupDraftData:
        row = connection.execute(
            """SELECT setup_draft_json FROM local_installations
               WHERE installation_id='local'"""
        ).fetchone()
        if row is None or row[0] is None:
            return _default_draft()

        return _parse_draft(str(row[0]))

    @staticmethod
    def save_for_transaction(
        connection: sqlite3.Connection, draft: SetupDraftData
    ) -> None:
        connection.execute(
            """UPDATE local_installations
               SET setup_draft_json=?, updated_at=CURRENT_TIMESTAMP
               WHERE installation_id='local'""",
            (json.dumps(draft, ensure_ascii=False),),
        )

    def record_for_transaction(
        self, connection: sqlite3.Connection
    ) -> SetupDraftRecord:
        draft = self.load_for_transaction(connection)
        return SetupDraftRecord(
            owner_account_id=_optional_text(draft.get("owner_account_id")),
            display_name=_optional_text(draft.get("display_name")),
            password_hash=_optional_text(draft.get("password_hash")),
            use_local_ollama=_optional_bool(draft.get("use_local_ollama")),
            model_id=_optional_text(draft.get("model_id")),
            bed_count=_optional_int(draft.get("bed_count")),
            owner_configured=draft["owner_configured"],
            offline_configured=draft["offline_configured"],
            nest_configured=draft["nest_configured"],
            locked_at=_optional_text(draft.get("locked_at")),
        )


def _default_draft() -> SetupDraftData:
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


def _parse_draft(raw_json: str) -> SetupDraftData:
    try:
        loaded = json.loads(raw_json)
        if not isinstance(loaded, dict):
            raise ValueError("草稿数据不是对象")
        values: Mapping[str, SetupDraftValue] = loaded
        return {
            "owner_account_id": _optional_text(values.get("owner_account_id")),
            "display_name": _optional_text(values.get("display_name")),
            "password_hash": _optional_text(values.get("password_hash")),
            "use_local_ollama": _optional_bool(values.get("use_local_ollama")),
            "model_id": _optional_text(values.get("model_id")),
            "bed_count": _optional_int(values.get("bed_count")),
            "owner_configured": _flag(values.get("owner_configured")),
            "offline_configured": _flag(values.get("offline_configured")),
            "nest_configured": _flag(values.get("nest_configured")),
            "locked_at": _optional_text(values.get("locked_at")),
        }
    except (TypeError, ValueError) as error:
        raise RuntimeError("Setup 草稿字段无效") from error


def _optional_text(value: SetupDraftValue) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("草稿文本字段类型无效")


def _optional_int(value: SetupDraftValue) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("草稿整数字段类型无效")
    return value


def _optional_bool(value: SetupDraftValue) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("草稿布尔字段类型无效")
    return value


def _flag(value: SetupDraftValue) -> bool:
    return _optional_bool(value) is True
