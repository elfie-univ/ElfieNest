"""SQLite 持久化层 — users/sessions/elfie_registry 表 + Owner seed。

首次启动自动创建 nest.db，含 3 张表。
提供 get_db() 上下文管理器保证线程安全连接。
"""

import hashlib
import logging
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from elfienest.persistence.schema import initialize_schema, migrate_schema
from runtime.storage.data_home import get_db_path as _get_db_path

logger = logging.getLogger("elfienest.persistence.store")

# ---------------------------------------------------------------------------
# Password Hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 password hashing.

    Output format: ``pbkdf2_sha256$260000$<salt>$<hash>``

    Args:
        password: Plaintext password to hash.

    Returns:
        Encoded hash string that can be stored in the database.
    """
    salt = secrets.token_hex(16)
    iterations = 260_000
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a previously generated pbkdf2_sha256 hash.

    Args:
        password: Plaintext password to verify.
        hashed: Hash string previously returned by :func:`hash_password`.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    parts = hashed.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    iterations = int(parts[1])
    salt = parts[2]
    expected_hash = parts[3]
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return secrets.compare_digest(dk.hex(), expected_hash)


# ---------------------------------------------------------------------------
# Database Initialization & Seeding
# ---------------------------------------------------------------------------


def init_db(db_path: Optional[str] = None) -> str:
    """Initialize the database and create all required tables.

    Creates the parent ``data/`` directory if it does not exist.  Tables are
    created with ``CREATE TABLE IF NOT EXISTS`` so the call is idempotent.

    Args:
        db_path: Path to the SQLite database file.  Defaults to ``data/nest.db``
            relative to the current working directory.

    Returns:
        The resolved absolute path of the database file.
    """
    if db_path is None:
        db_path = str(_get_db_path())

    resolved = Path(db_path).resolve()
    parent_existed = resolved.parent.exists()
    resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # 仅收紧为此数据库新建的目录；显式配置的路径可能位于 /tmp 等共享目录，
    # 初始化数据库时不能修改共享目录权限。
    if os.name != "nt" and not parent_existed:
        resolved.parent.chmod(0o700)

    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    initialize_schema(conn)
    conn.commit()
    conn.close()
    if os.name != "nt":
        resolved.chmod(0o600)
    logger.info("Database initialized at %s", resolved)
    return str(resolved)


def migrate_db_if_needed(db_path: Optional[str] = None) -> None:
    """检查并执行必要的数据库迁移。使用 PRAGMA user_version 跟踪版本。"""
    if db_path is None:
        db_path = str(_get_db_path())
    with get_db(db_path) as conn:
        migrate_schema(conn)


def seed_initial_owner_if_env_set(
    db_path: Optional[str] = None,
    username_env: str = "OWNER_USERNAME",
    password_env: str = "OWNER_PASSWORD",
) -> bool:
    """从 Owner 环境变量创建唯一 Owner 账户。"""
    return _seed_initial_account_from_env(
        db_path,
        username_env=username_env,
        password_env=password_env,
        role="owner",
    )


def _seed_initial_account_from_env(
    db_path: Optional[str],
    *,
    username_env: str,
    password_env: str,
    role: str,
) -> bool:
    if db_path is None:
        db_path = str(_get_db_path())
    username = os.environ.get(username_env, "")
    password = os.environ.get(password_env, "")

    if not username or not password:
        return False

    with get_db(db_path) as conn:
        if role == "owner":
            conn.execute("BEGIN IMMEDIATE")
        # 检查是否已存在
        cursor = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            return False

        pw_hash = hash_password(password)
        if role == "owner":
            owner = conn.execute(
                "SELECT id FROM users WHERE role = 'owner' LIMIT 1"
            ).fetchone()
            if owner is not None:
                return False
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pw_hash, role),
            )
        except sqlite3.IntegrityError:
            return False
        conn.commit()
        logger.info("从环境变量创建了初始 %s: %s", role, username)
        return True


# ---------------------------------------------------------------------------
# Connection Context Manager
# ---------------------------------------------------------------------------


@contextmanager
def get_db(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    """Context manager that yields a new SQLite connection and closes it on exit.

    Every call opens a fresh connection — this is intentional to avoid
    cross-thread sharing issues with FastAPI.

    Args:
        db_path: Path to the SQLite database file.  Defaults to ``data/nest.db``.

    Yields:
        An open :class:`sqlite3.Connection` with ``row_factory`` set to
        :class:`sqlite3.Row` and ``PRAGMA foreign_keys = ON``.
    """
    if db_path is None:
        db_path = str(_get_db_path())

    if db_path != ":memory:":
        database_path = Path(db_path).expanduser().resolve()
        if database_path.exists() and os.name != "nt":
            database_path.chmod(0o600)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Query Helpers
# ---------------------------------------------------------------------------


def count_elfies_by_owner(user_id: int, db_path: Optional[str] = None) -> int:
    """Return the number of elfies currently owned by *user_id*.

    Used by the adoption endpoint to enforce the per-user limit (max 3).

    Args:
        user_id: The user's database ``id``.
        db_path: Path to the SQLite database file.  Defaults to ``~/.elfienest/nest.db``.

    Returns:
        Elfie count for the given owner.
    """
    with get_db(db_path) as db:
        cursor = db.execute(
            "SELECT COUNT(*) AS cnt FROM elfie_registry WHERE owner_user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return row["cnt"] if row else 0
