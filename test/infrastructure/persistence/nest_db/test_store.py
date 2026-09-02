"""测试根持久化 store — init_db / seed_initial_owner_if_env_set / get_db / count_elfies_by_owner

使用 tmp_path 隔离每个测试的 DB 文件。
"""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from infrastructure.persistence.layout.data_home import DataHomeSelectionError
from infrastructure.persistence.nest_db.store import (
    count_elfies_by_owner,
    get_db,
    init_db,
)
from test.app.interfaces.api._helpers import create_test_owner


def _table_names(db_path: str) -> set[str]:
    """返回数据库中所有用户表的名称集合。"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    return tables


def _index_names(db_path: str) -> set[str]:
    """返回数据库中所有索引的集合。"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
    )
    idxs = {row[0] for row in cursor.fetchall() if row[0] is not None}
    conn.close()
    return idxs


class TestInitDb:
    def test_rejects_in_memory_marker_without_creating_layout(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.chdir(tmp_path)

        with pytest.raises(DataHomeSelectionError, match="内存数据库"):
            init_db(":memory:")

        assert not any(tmp_path.iterdir())

    def test_does_not_change_existing_parent_permissions(self, tmp_path: Path) -> None:
        parent_mode = stat.S_IMODE(tmp_path.stat().st_mode)

        init_db(str(tmp_path / "nest.db"))

        assert stat.S_IMODE(tmp_path.stat().st_mode) == parent_mode

    def test_creates_core_tables(self, tmp_path: Path) -> None:
        db = str(tmp_path / "nest.db")
        init_db(db)

        tables = _table_names(db)
        assert "users" in tables
        assert "sessions" in tables
        assert tables == {
            "device_audit_events",
            "elfies",
            "embodiment_sessions",
            "external_bodies",
            "food_packages",
            "local_installations",
            "nest_settings",
            "resident_admissions",
            "sessions",
            "users",
        }

    def test_creates_indices(self, tmp_path: Path) -> None:
        """init_db 创建必要的索引（至少 users.account_id 有 UNIQUE 索引）。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        indices = {n.lower() for n in _index_names(db)}
        # sqlite 为 UNIQUE 约束自动创建的索引名是 sqlite_autoindex_users_1 之类的
        auto_idx = {n for n in indices if "autoindex" in n}
        assert len(auto_idx) >= 1  # 至少 users.account_id 的 UNIQUE 索引

    def test_idempotent(self, tmp_path: Path) -> None:
        """init_db 幂等 — 多次调用不报错。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        init_db(db)  # 第二次不应抛异常
        tables = _table_names(db)
        assert "users" in tables


class TestGetDb:
    def test_context_manager_closes_connection(self, tmp_path: Path) -> None:
        """get_db 上下文管理器正常关闭连接。"""
        db = str(tmp_path / "nest.db")
        init_db(db)

        with get_db(db) as conn:
            assert isinstance(conn, sqlite3.Connection)
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone() is not None

        # 上下文退出后连接应已关闭
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_row_factory_is_sqlite3_row(self, tmp_path: Path) -> None:
        """get_db 返回的连接 row_factory 为 sqlite3.Row。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        with get_db(db) as conn:
            assert conn.row_factory is sqlite3.Row

    def test_foreign_keys_on(self, tmp_path: Path) -> None:
        """get_db 设置 PRAGMA foreign_keys = ON。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        with get_db(db) as conn:
            cursor = conn.execute("PRAGMA foreign_keys")
            assert cursor.fetchone()[0] == 1


class TestCountElfiesByOwner:
    def test_zero(self, tmp_path: Path) -> None:
        """无精灵时返回 0。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        owner_id = create_test_owner(db)

        assert count_elfies_by_owner(owner_id, db) == 0

    def test_one(self, tmp_path: Path) -> None:
        """一个精灵时返回 1。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        owner_id = create_test_owner(db)

        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO elfies "
                "(elfie_id, owner_user_id, adopted_at, status) "
                "VALUES (?, ?, CURRENT_TIMESTAMP, 'offline')",
                ("00000001", owner_id),
            )
            conn.commit()

        assert count_elfies_by_owner(owner_id, db) == 1

    def test_two(self, tmp_path: Path) -> None:
        """两个精灵时返回 2。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        owner_id = create_test_owner(db)

        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO elfies "
                "(elfie_id, owner_user_id, adopted_at, status) "
                "VALUES (?, ?, CURRENT_TIMESTAMP, 'offline')",
                ("00000001", owner_id),
            )
            conn.execute(
                "INSERT INTO elfies "
                "(elfie_id, owner_user_id, adopted_at, status) "
                "VALUES (?, ?, CURRENT_TIMESTAMP, 'offline')",
                ("00000002", owner_id),
            )
            conn.commit()

        assert count_elfies_by_owner(owner_id, db) == 2
