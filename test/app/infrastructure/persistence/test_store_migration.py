"""测试 store.py — migrate_db_if_needed / 数据库版本迁移

测试用例覆盖：
- v1→v2 迁移：添加 nickname / avatar_color / avatar_kind 三列
- 幂等性：重复执行迁移不报错
- 数据保持：迁移前插入的用户数据在迁移后完整
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.schema import OwnerSchemaMigrationError
from app.infrastructure.persistence.store import init_db, migrate_db_if_needed


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
    def test_unknown_role_requires_explicit_migration(self, tmp_path: Path) -> None:
        """未知角色不得被静默改成 Owner 或 user。"""
        db = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("legacy-admin", "hash", "admin"),
        )
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
        conn.close()

        with pytest.raises(OwnerSchemaMigrationError, match="admin") as error_info:
            migrate_db_if_needed(db)

        backup_paths = tuple(tmp_path.glob("legacy.db.migration-backup.*"))
        assert len(backup_paths) == 1
        assert "原数据库备份已保留" in str(error_info.value)
        assert backup_paths[0].read_bytes() == Path(db).read_bytes()

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT role FROM users").fetchone()[0] == "admin"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
            ).fetchone()
            is None
        )
        conn.close()

    def test_multiple_owners_require_explicit_migration(self, tmp_path: Path) -> None:
        """多个 Owner 不得被静默降级，迁移失败时保留原 schema。"""
        db = str(tmp_path / "multiple-owners.db")
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('owner', 'user')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.executemany(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            [("owner-one", "hash-1"), ("owner-two", "hash-2")],
        )
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
        conn.close()

        with pytest.raises(OwnerSchemaMigrationError, match="2 个 Owner"):
            migrate_db_if_needed(db)

        conn = sqlite3.connect(db)
        assert (
            conn.execute("SELECT COUNT(*) FROM users WHERE role = 'owner'").fetchone()[
                0
            ]
            == 2
        )
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert "updated_at" not in _table_info_columns(db)
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
            ).fetchone()
            is None
        )
        conn.close()

    def test_adds_profile_columns(self, tmp_path: Path) -> None:
        """迁移后 users 表包含 nickname / avatar_color / avatar_kind 三列。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)

        cols = _table_info_columns(db)
        assert "nickname" in cols
        assert "avatar_color" in cols
        assert "avatar_kind" in cols

    def test_user_version_becomes_10(self, tmp_path: Path) -> None:
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)

        assert _user_version(db) == 10

    def test_migration_idempotent(self, tmp_path: Path) -> None:
        """重复执行 migrate_db_if_needed 不报错。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)
        migrate_db_if_needed(db)  # 第二次不应抛异常

        cols = _table_info_columns(db)
        assert "nickname" in cols
        assert _user_version(db) == 10

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
            ("owner", "pbkdf2_sha256$260000$ccdd$hash", "owner"),
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

        assert rows[1]["username"] == "owner"
        assert rows[1]["role"] == "owner"
        assert rows[1]["nickname"] is None

    def test_column_count(self, tmp_path: Path) -> None:
        """迁移后 users 表包含 Owner 的默认落页偏好。"""
        db = str(tmp_path / "nest.db")
        init_db(db)
        migrate_db_if_needed(db)

        cols = _table_info_columns(db)
        assert len(cols) == 10
        # 验证列顺序：原 5 列 + updated_at + profile 3 列 + 默认落页
        assert cols[:5] == ["id", "username", "password_hash", "role", "created_at"]
        assert cols[5:] == [
            "updated_at",
            "nickname",
            "avatar_color",
            "avatar_kind",
            "default_landing_page",
        ]

    def test_init_db_sets_version_10_without_legacy_chat_table(self, tmp_path: Path) -> None:
        db = str(tmp_path / "nest.db")
        init_db(db)

        cols = _table_info_columns(db)
        assert "nickname" in cols
        assert _user_version(db) == 10
        connection = sqlite3.connect(db)
        legacy_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_messages'"
        ).fetchone()
        connection.close()
        assert legacy_table is None

    def test_v9_database_deletes_the_unreleased_legacy_chat_table(
        self, tmp_path: Path
    ) -> None:
        db = str(tmp_path / "legacy-v9.db")
        init_db(db)
        with sqlite3.connect(db) as connection:
            connection.execute("PRAGMA user_version = 9")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY,
                    elfie_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL
                )
                """
            )

        migrate_db_if_needed(db)

        connection = sqlite3.connect(db)
        legacy_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_messages'"
        ).fetchone()
        connection.close()
        assert _user_version(db) == 10
        assert legacy_table is None

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
        assert "species_id" in elfie_cols
        assert "profile_schema_version" in elfie_cols

    def test_v5_registry_migrates_with_stable_species_defaults(
        self, tmp_path: Path
    ) -> None:
        db = str(tmp_path / "v5.db")
        conn = sqlite3.connect(db)
        conn.execute(
            """CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('owner', 'user')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                nickname TEXT DEFAULT NULL,
                avatar_color INTEGER DEFAULT 0,
                avatar_kind TEXT DEFAULT 'initials'
            )"""
        )
        conn.execute(
            """CREATE TABLE elfie_registry (
                id INTEGER PRIMARY KEY,
                elfie_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                owner_user_id INTEGER,
                anatomy_type TEXT DEFAULT 'biped',
                config_dir TEXT,
                personality_style TEXT,
                height TEXT DEFAULT 'standard',
                build TEXT DEFAULT 'standard',
                bed_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            "INSERT INTO elfie_registry (elfie_id, name, anatomy_type) VALUES (?, ?, ?)",
            ("legacy-1", "旧精灵", "quadruped"),
        )
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
        conn.close()

        migrate_db_if_needed(db)

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT elfie_id, anatomy_type, species_id, profile_schema_version "
            "FROM elfie_registry WHERE elfie_id = 'legacy-1'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["anatomy_type"] == "quadruped"
        assert row["species_id"] == "fox"
        assert row["profile_schema_version"] == 1
        assert _user_version(db) == 10
