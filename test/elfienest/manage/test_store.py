"""测试 store.py — init_db / seed_admin / get_db / count_elfies_by_owner

使用 tmp_path 隔离每个测试的 DB 文件。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from elfienest.manage.store import (
    count_elfies_by_owner,
    get_db,
    init_db,
    seed_admin,
)


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
    def test_creates_three_tables(self, tmp_path: Path) -> None:
        """init_db 创建 users / sessions / elfie_registry 三张表。"""
        db = str(tmp_path / "nest.db")
        init_db(db)

        tables = _table_names(db)
        assert "users" in tables
        assert "sessions" in tables
        assert "elfie_registry" in tables
        # 自动创建的 sqlite_* 表不计
        assert len(tables) >= 3

    def test_creates_indices(self, tmp_path: Path) -> None:
        """init_db 创建必要的索引（至少 users.username 有 UNIQUE 索引）。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        indices = {n.lower() for n in _index_names(db)}
        # sqlite 为 UNIQUE 约束自动创建的索引名是 sqlite_autoindex_users_1 之类的
        auto_idx = {n for n in indices if "autoindex" in n}
        assert len(auto_idx) >= 1  # 至少 users.username 的 UNIQUE 索引

    def test_idempotent(self, tmp_path: Path) -> None:
        """init_db 幂等 — 多次调用不报错。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        init_db(db)  # 第二次不应抛异常
        tables = _table_names(db)
        assert "users" in tables


class TestSeedAdmin:
    def test_creates_admin_when_empty(self, tmp_path: Path) -> None:
        """seed_admin 在空表时插入 admin 用户。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        seed_admin(db)

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE username = ?", ("admin",)).fetchone()
        conn.close()

        assert row is not None
        assert row["username"] == "admin"
        assert row["role"] == "admin"
        # 密码是 PBKDF2 格式: pbkdf2_sha256$260000$...$...
        pw_hash: str = row["password_hash"]
        assert pw_hash.startswith("pbkdf2_sha256$260000$")
        parts = pw_hash.split("$")
        assert len(parts) == 4
        assert len(parts[2]) == 32  # 16 字节 hex salt
        assert len(parts[3]) == 64  # SHA256 → 32 字节 hex

    def test_does_not_reinsert_when_not_empty(self, tmp_path: Path) -> None:
        """seed_admin 在非空表时不重复插入。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        seed_admin(db)
        seed_admin(db)  # 第二次

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()[0]
        conn.close()
        assert count == 1  # 只有一个 admin


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
        seed_admin(db)

        # 获取 admin id
        conn = sqlite3.connect(db)
        admin_id = conn.execute(
            "SELECT id FROM users WHERE username='admin'"
        ).fetchone()[0]
        conn.close()

        assert count_elfies_by_owner(admin_id, db) == 0

    def test_one(self, tmp_path: Path) -> None:
        """一个精灵时返回 1。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        seed_admin(db)

        conn = sqlite3.connect(db)
        admin_id = conn.execute(
            "SELECT id FROM users WHERE username='admin'"
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
            "VALUES (?, ?, ?)",
            ("elfie_001", "小白", admin_id),
        )
        conn.commit()
        conn.close()

        assert count_elfies_by_owner(admin_id, db) == 1

    def test_two(self, tmp_path: Path) -> None:
        """两个精灵时返回 2。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        seed_admin(db)

        conn = sqlite3.connect(db)
        admin_id = conn.execute(
            "SELECT id FROM users WHERE username='admin'"
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
            "VALUES (?, ?, ?)",
            ("elfie_001", "小白", admin_id),
        )
        conn.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
            "VALUES (?, ?, ?)",
            ("elfie_002", "小黑", admin_id),
        )
        conn.commit()
        conn.close()

        assert count_elfies_by_owner(admin_id, db) == 2
