"""SQLite 持久化层 — users/sessions/elfie_registry 表 + seed admin。

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
    resolved.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    _ensure_nest_tables(conn)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS elfie_registry (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_user_id) REFERENCES users(id),
            FOREIGN KEY(bed_id) REFERENCES beds(id)
        )
    """)

    # --- Schema migration tracking ---
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        conn.execute("PRAGMA user_version = 1")
    if version < 2:
        # v1 → v2: add profile fields
        _migrate_v1_to_v2(conn)
    if version < 3:
        _migrate_v2_to_v3(conn)
    if version < 4:
        _migrate_v3_to_v4(conn)

    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", resolved)
    return str(resolved)


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Apply v1→v2 schema migration (add profile columns) with per-statement error handling."""
    for stmt in [
        "ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN avatar_color INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN avatar_kind TEXT DEFAULT 'initials'",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.execute("PRAGMA user_version = 2")


def _ensure_nest_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            max_capacity INTEGER NOT NULL DEFAULT 4,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS beds (
            id INTEGER PRIMARY KEY,
            room_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            grid_x INTEGER DEFAULT 0,
            grid_y INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
    """)


def _ensure_chat_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY,
            elfie_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            sender TEXT NOT NULL CHECK(sender IN ('user', 'elfie', 'system')),
            text TEXT NOT NULL,
            meta TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(elfie_id) REFERENCES elfie_registry(elfie_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_lookup
        ON chat_messages(elfie_id, user_id, created_at)
    """)


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    _ensure_nest_tables(conn)
    try:
        conn.execute("ALTER TABLE elfie_registry ADD COLUMN bed_id INTEGER")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA user_version = 3")


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    _ensure_chat_tables(conn)
    conn.execute("PRAGMA user_version = 4")


def migrate_db_if_needed(db_path: str = None) -> None:
    """检查并执行必要的数据库迁移。使用 PRAGMA user_version 跟踪版本。"""
    if db_path is None:
        db_path = str(_get_db_path())
    with get_db(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.execute("PRAGMA user_version = 1")
        if version < 2:
            _migrate_v1_to_v2(conn)
        if version < 3:
            _migrate_v2_to_v3(conn)
        if version < 4:
            _migrate_v3_to_v4(conn)
        conn.commit()


def seed_initial_admin_if_env_set(
    db_path: str = None,
    username_env: str = "ADMIN_USERNAME",
    password_env: str = "ADMIN_PASSWORD",
) -> bool:
    """如果环境变量设置了管理员凭据，则创建初始管理员。

    Returns:
        True 如果创建了管理员，False 如果环境变量未设置或用户已存在。
    """
    if db_path is None:
        db_path = str(_get_db_path())
    username = os.environ.get(username_env, "")
    password = os.environ.get(password_env, "")

    if not username or not password:
        return False

    with get_db(db_path) as conn:
        # 检查是否已存在
        cursor = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            return False

        pw_hash = hash_password(password)
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (username, pw_hash),
        )
        conn.commit()
        logger.info("从环境变量创建了初始管理员: %s", username)
        return True


def seed_admin(db_path: Optional[str] = None) -> None:
    """已弃用: 请使用 :func:`seed_initial_admin_if_env_set`。

    旧版函数保留用于向后兼容。现在内部调用
    ``seed_initial_admin_if_env_set``，不再硬编码管理员凭据。
    """
    import warnings  # noqa: PLC0415

    warnings.warn(
        "seed_admin 已弃用，请使用 seed_initial_admin_if_env_set",
        DeprecationWarning,
        stacklevel=2,
    )
    seed_initial_admin_if_env_set(db_path=db_path or str(_get_db_path()))


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
