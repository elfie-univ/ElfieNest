"""SQLite relations between users, Elfies and external food-package IDs."""

from __future__ import annotations

from app.infrastructure.persistence.store import get_db


def get_elfie_main_food_id(db_path: str, elfie_id: str) -> str | None:
    with get_db(db_path) as connection:
        row = connection.execute(
            """
            SELECT main_food_id
            FROM elfies
            WHERE elfie_id = ?
            """,
            (elfie_id,),
        ).fetchone()
    if row is None or row["main_food_id"] is None:
        return None
    return str(row["main_food_id"])


def get_elfie_owner_user_id(db_path: str, elfie_id: str) -> int | None:
    with get_db(db_path) as connection:
        row = connection.execute(
            """
            SELECT owner_user_id
            FROM elfies
            WHERE elfie_id = ?
            """,
            (elfie_id,),
        ).fetchone()
    if row is None or row["owner_user_id"] is None:
        return None
    return int(row["owner_user_id"])


def set_elfie_main_food_id(
    db_path: str,
    elfie_id: str,
    food_key: str,
) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            """
            UPDATE elfies
            SET main_food_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE elfie_id = ?
            """,
            (food_key, elfie_id),
        )
        connection.commit()


def food_assignment_usage(db_path: str, food_key: str) -> dict[str, int]:
    with get_db(db_path) as connection:
        elfies = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM elfies
                WHERE main_food_id = ?
                """,
                (food_key,),
            ).fetchone()[0]
        )
    return {"users": 0, "elfies": elfies}
