"""Card 15 transactional account field and avatar cutover tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.account_avatar_storage import AvatarStorageError
from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.account_storage_cutover import (
    AccountStorageCutoverError,
    ensure_account_storage_cutover,
)
from app.infrastructure.persistence.store import get_db, init_db


def test_cutover_copies_valid_avatar_and_freezes_legacy_quota(
    tmp_path: Path,
) -> None:
    # Given: one legacy user and a signature-valid avatar under the old root.
    db_path = init_db(str(tmp_path / "nest.db"))
    legacy_avatar = tmp_path / "avatars" / "users" / "1.png"
    legacy_avatar.parent.mkdir(parents=True)
    image = b"\x89PNG\r\n\x1a\nlegacy-image"
    legacy_avatar.write_bytes(image)
    with get_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO users
                (id, username, password_hash, role, avatar_path,
                 elfie_quota_override)
            VALUES (1, 'alice', 'hash', 'user', 'avatars/users/1.png', 7)
            """
        )
        connection.commit()

    # When: Card 15 is applied twice around a final NULL quota update.
    ensure_account_storage_cutover(db_path)
    final_avatar = tmp_path / "assets" / "users" / "1" / "avatar.png"
    with get_db(db_path) as connection:
        repository = AccountRepository(connection)
        repository.update_quota(1, None)
        connection.commit()
    ensure_account_storage_cutover(db_path)

    # Then: copy semantics and final-only quota writes survive restart.
    assert legacy_avatar.read_bytes() == image
    assert final_avatar.read_bytes() == image
    with get_db(db_path) as connection:
        row = connection.execute(
            """
            SELECT avatar_path, elfie_limit, elfie_quota_override
            FROM users WHERE id = 1
            """
        ).fetchone()
        assert row["avatar_path"] == "assets/users/1/avatar.png"
        assert row["elfie_limit"] is None
        assert row["elfie_quota_override"] == 7
        with pytest.raises(sqlite3.IntegrityError, match="legacy elfie quota"):
            connection.execute(
                "UPDATE users SET elfie_quota_override = 8 WHERE id = 1"
            )


@pytest.mark.parametrize(
    ("stored_path", "payload"),
    (
        ("avatars/users/1.svg", b"<svg></svg>"),
        ("avatars/users/1.png", b"not-a-png"),
        ("avatars/users/../escape.png", None),
        ("avatars/users/1.webp", None),
        ("avatars/users/1.jpg", b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024)),
    ),
)
def test_invalid_legacy_avatar_rolls_back_entire_cutover(
    tmp_path: Path,
    stored_path: str,
    payload: bytes | None,
) -> None:
    # Given: one legacy account whose avatar metadata or file is unsafe.
    db_path = init_db(str(tmp_path / "nest.db"))
    if payload is not None:
        source = tmp_path.joinpath(*stored_path.split("/"))
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
    with get_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO users
                (id, username, password_hash, role, avatar_path,
                 elfie_quota_override)
            VALUES (1, 'alice', 'hash', 'user', ?, 4)
            """,
            (stored_path,),
        )
        connection.commit()

    # When/Then: no final column, path, or copied file survives the failure.
    with pytest.raises(AvatarStorageError):
        ensure_account_storage_cutover(db_path)
    with get_db(db_path) as connection:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        avatar_path = connection.execute(
            "SELECT avatar_path FROM users WHERE id = 1"
        ).fetchone()["avatar_path"]
    assert "elfie_limit" not in columns
    assert avatar_path == stored_path
    assert not (tmp_path / "assets").exists()


@pytest.mark.parametrize(("role", "quota"), (("", 3), ("user", 33)))
def test_invalid_legacy_account_rolls_back_new_columns(
    tmp_path: Path,
    role: str,
    quota: int,
) -> None:
    # Given: an adversarial legacy table without the normal CHECK constraints.
    db_path = tmp_path / "nest.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                password_hash TEXT,
                role TEXT,
                created_at TEXT,
                updated_at TEXT,
                avatar_path TEXT,
                elfie_quota_override INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO users
                (id, username, password_hash, role, created_at, updated_at,
                 avatar_path, elfie_quota_override)
            VALUES (1, 'alice', 'hash', ?, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP, NULL, ?)
            """,
            (role, quota),
        )

    # When/Then: validation aborts the same transaction that added columns.
    with pytest.raises(AccountStorageCutoverError):
        ensure_account_storage_cutover(str(db_path))
    with sqlite3.connect(db_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(users)")
        }
    assert "gender" not in columns
    assert "elfie_limit" not in columns


def test_avatar_cutover_rejects_symlinked_target_ancestor(tmp_path: Path) -> None:
    # Given: the final assets ancestor redirects outside the data root.
    db_path = init_db(str(tmp_path / "nest.db"))
    legacy_avatar = tmp_path / "avatars" / "users" / "1.png"
    legacy_avatar.parent.mkdir(parents=True)
    legacy_avatar.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    escape = tmp_path.parent / f"{tmp_path.name}-escape"
    escape.mkdir()
    (tmp_path / "assets").symlink_to(escape, target_is_directory=True)
    with get_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO users
                (id, username, password_hash, role, avatar_path)
            VALUES (1, 'alice', 'hash', 'user', 'avatars/users/1.png')
            """
        )
        connection.commit()

    # When/Then: neither the redirect target nor final DB fields are written.
    with pytest.raises(AvatarStorageError, match="symlink|outside"):
        ensure_account_storage_cutover(db_path)
    assert not (escape / "users" / "1" / "avatar.png").exists()
    with get_db(db_path) as connection:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
    assert "elfie_limit" not in columns


def test_late_avatar_copy_conflict_cleans_new_targets_and_rolls_back(
    tmp_path: Path,
) -> None:
    # Given: two valid legacy avatars but a conflicting second final target.
    db_path = init_db(str(tmp_path / "nest.db"))
    for user_id in (1, 2):
        source = tmp_path / "avatars" / "users" / f"{user_id}.png"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([user_id]))
    conflicting = tmp_path / "assets" / "users" / "2" / "avatar.png"
    conflicting.parent.mkdir(parents=True)
    conflicting.write_bytes(b"\x89PNG\r\n\x1a\nconflict")
    with get_db(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO users
                (id, username, password_hash, role, avatar_path)
            VALUES (?, ?, 'hash', 'user', ?)
            """,
            (
                (1, "alice", "avatars/users/1.png"),
                (2, "bob", "avatars/users/2.png"),
            ),
        )
        connection.commit()

    # When/Then: the first new copy is removed and the pre-existing file survives.
    with pytest.raises(AvatarStorageError, match="different bytes"):
        ensure_account_storage_cutover(db_path)
    assert not (tmp_path / "assets" / "users" / "1" / "avatar.png").exists()
    assert conflicting.read_bytes() == b"\x89PNG\r\n\x1a\nconflict"
    with get_db(db_path) as connection:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
    assert "elfie_limit" not in columns
