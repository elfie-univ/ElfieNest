"""SQLite relations between users, Elfies and external food-package IDs."""

from __future__ import annotations

from collections.abc import Iterable

from app.infrastructure.persistence.store import get_db


def list_user_food_access(db_path: str, user_id: int) -> tuple[str, ...]:
    with get_db(db_path) as connection:
        rows = connection.execute(
            """
            SELECT food_key
            FROM food_package_access
            WHERE user_id = ?
            ORDER BY food_key
            """,
            (user_id,),
        ).fetchall()
    return tuple(str(row["food_key"]) for row in rows)


def replace_user_food_access(
    db_path: str,
    user_id: int,
    food_keys: Iterable[str],
) -> tuple[str, ...]:
    normalized = tuple(
        sorted(
            {str(food_key).strip() for food_key in food_keys if str(food_key).strip()}
        )
    )
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM food_package_access WHERE user_id = ?",
            (user_id,),
        )
        connection.executemany(
            "INSERT INTO food_package_access (user_id, food_key) VALUES (?, ?)",
            ((user_id, food_key) for food_key in normalized),
        )
        connection.commit()
    return normalized


def list_food_access_users(db_path: str, food_key: str) -> tuple[int, ...]:
    with get_db(db_path) as connection:
        rows = connection.execute(
            """
            SELECT user_id
            FROM food_package_access
            WHERE food_key = ?
            ORDER BY user_id
            """,
            (food_key,),
        ).fetchall()
    return tuple(int(row["user_id"]) for row in rows)


def replace_food_access_users(
    db_path: str,
    food_key: str,
    user_ids: Iterable[int],
) -> tuple[int, ...]:
    normalized = tuple(sorted({int(user_id) for user_id in user_ids}))
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM food_package_access WHERE food_key = ?",
            (food_key,),
        )
        connection.executemany(
            "INSERT INTO food_package_access (user_id, food_key) VALUES (?, ?)",
            ((user_id, food_key) for user_id in normalized),
        )
        connection.commit()
    return normalized


def get_elfie_primary_food(db_path: str, elfie_id: str) -> str | None:
    with get_db(db_path) as connection:
        row = connection.execute(
            """
            SELECT primary_food_key
            FROM elfie_food_preferences
            WHERE elfie_id = ?
            """,
            (elfie_id,),
        ).fetchone()
    return str(row["primary_food_key"]) if row is not None else None


def get_elfie_owner_user_id(db_path: str, elfie_id: str) -> int | None:
    with get_db(db_path) as connection:
        row = connection.execute(
            """
            SELECT owner_user_id
            FROM elfie_registry
            WHERE elfie_id = ?
            """,
            (elfie_id,),
        ).fetchone()
    if row is None or row["owner_user_id"] is None:
        return None
    return int(row["owner_user_id"])


def set_elfie_primary_food(
    db_path: str,
    elfie_id: str,
    food_key: str,
) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO elfie_food_preferences
                (elfie_id, primary_food_key, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(elfie_id) DO UPDATE SET
                primary_food_key = excluded.primary_food_key,
                updated_at = CURRENT_TIMESTAMP
            """,
            (elfie_id, food_key),
        )
        connection.commit()


def food_assignment_usage(db_path: str, food_key: str) -> dict[str, int]:
    with get_db(db_path) as connection:
        users = int(
            connection.execute(
                "SELECT COUNT(*) FROM food_package_access WHERE food_key = ?",
                (food_key,),
            ).fetchone()[0]
        )
        elfies = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM elfie_food_preferences
                WHERE primary_food_key = ?
                """,
                (food_key,),
            ).fetchone()[0]
        )
    return {"users": users, "elfies": elfies}
