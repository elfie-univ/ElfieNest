"""SQLite 持久化层 — users/sessions/elfie_registry 表 + seed admin。

首次启动自动创建 data/nest.db，含 3 张表。
提供 get_db() 上下文管理器保证线程安全连接。
"""

import hashlib
import logging
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger("elfienest.manage.store")

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
        db_path = "data/nest.db"

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", resolved)
    return str(resolved)


def seed_admin(db_path: Optional[str] = None) -> None:
    """Insert the default admin account if the ``users`` table is empty.

    The account is created with username ``admin`` and password
    ``adminchangeme`` (PBKDF2 hashed).  A prominent warning is printed to
    stdout.

    Args:
        db_path: Path to the SQLite database file.  Defaults to ``data/nest.db``.
    """
    if db_path is None:
        db_path = "data/nest.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS cnt FROM users")
    row = cursor.fetchone()
    count: int = row["cnt"] if row else 0

    if count == 0:
        pw_hash = hash_password("adminchangeme")
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", pw_hash, "admin"),
        )
        conn.commit()
        print("=" * 60)
        print("  WARNING: Default admin account created!")
        print("   Username: admin")
        print("   Password: adminchangeme")
        print("   Please change the password immediately.")
        print("=" * 60)
        logger.warning("Default admin account seeded (admin / adminchangeme)")

    conn.close()


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
        db_path = "data/nest.db"

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
        db_path: Path to the SQLite database file.  Defaults to ``data/nest.db``.

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
