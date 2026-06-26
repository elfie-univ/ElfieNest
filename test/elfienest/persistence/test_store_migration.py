"""测试 store.py — migrate_db_if_needed / 数据库版本迁移

测试用例覆盖：
- v1→v2 迁移：添加 nickname / avatar_color / avatar_kind 三列
- 幂等性：重复执行迁移不报错
- 数据保持：迁移前插入的用户数据在迁移后完整
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from elfienest.persistence.store import init_db, migrate_db_if_needed


def _user_version(db_path: str) -> int:
    """返回当前数据库的 PRAGMA user_version。"""
    conn = sqlite3.connect(db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return version


def _table_info_columns(db_path: str, table: str = "users") -> list[str]:
    """返回指定表的所有列名列表。"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    return columns


class TestMigrationV1ToV2:
    def test_adds_profile_columns(self, tmp_path: Path) -> None:
        """迁移后 users 表包含 nickname / avatar_color / avatar_kind 三列。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)

        cols = _table_info_columns(db)
        assert "nickname" in cols
        assert "avatar_color" in cols
        assert "avatar_kind" in cols

    def test_user_version_becomes_3(self, tmp_path: Path) -> None:
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)

        assert _user_version(db) == 3

    def test_migration_idempotent(self, tmp_path: Path) -> None:
        """重复执行 migrate_db_if_needed 不报错。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)
        migrate_db_if_needed(db)  # 第二次不应抛异常

        cols = _table_info_columns(db)
        assert "nickname" in cols
        assert _user_version(db) == 3

    def test_preserves_existing_data(self, tmp_path: Path) -> None:
        """迁移前插入的用户，迁移后数据保持完整。"""
        db = str(tmp_path / "nest.db")
        init_db(db)

        # 在 v1 数据库中插入用户
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("testuser", "pbkdf2_sha256$260000$aabb$hash", "user"),
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", "pbkdf2_sha256$260000$ccdd$hash", "admin"),
        )
        conn.commit()
        conn.close()

        # 执行迁移
        migrate_db_if_needed(db)

        # 验证数据完整
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0]["username"] == "testuser"
        assert rows[0]["role"] == "user"
        assert rows[0]["nickname"] is None
        assert rows[0]["avatar_color"] == 0
        assert rows[0]["avatar_kind"] == "initials"

        assert rows[1]["username"] == "admin"
        assert rows[1]["role"] == "admin"
        assert rows[1]["nickname"] is None

    def test_column_count(self, tmp_path: Path) -> None:
        """迁移后 users 表共有 8 列。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)

        cols = _table_info_columns(db)
        assert len(cols) == 8
        # 验证列顺序：原 5 列 + 新 3 列
        assert cols[:5] == ["id", "username", "password_hash", "role", "created_at"]
        assert cols[5:] == ["nickname", "avatar_color", "avatar_kind"]

    def test_init_db_sets_version_3(self, tmp_path: Path) -> None:
        db = str(tmp_path / "nest.db")
        init_db(db)

        cols = _table_info_columns(db)
        assert "nickname" in cols
        assert _user_version(db) == 3

    def test_adds_nest_tables_and_bed_id(self, tmp_path: Path) -> None:
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)

        room_cols = _table_info_columns(db, "rooms")
        bed_cols = _table_info_columns(db, "beds")
        elfie_cols = _table_info_columns(db, "elfie_registry")

        assert "name" in room_cols
        assert "max_capacity" in room_cols
        assert "room_id" in bed_cols
        assert "grid_x" in bed_cols
        assert "grid_y" in bed_cols
        assert "bed_id" in elfie_cols
