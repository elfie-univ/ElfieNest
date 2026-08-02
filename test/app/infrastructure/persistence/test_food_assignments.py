from app.infrastructure.persistence.food_assignments import (
    get_elfie_main_food_id,
    get_elfie_owner_user_id,
    list_user_food_access,
    replace_user_food_access,
    set_elfie_main_food_id,
)
from app.infrastructure.persistence.store import get_db, init_db


def test_food_assignments_store_only_stable_external_ids(tmp_path):
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES ('u01', 'h', 'user')"
        )
        user_id = int(
            connection.execute(
                "SELECT id FROM users WHERE account_id='u01'"
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO elfies (elfie_id, name, owner_user_id, species, adopted_at, status)
            VALUES ('12345678', 'Elfie', ?, 'fox', '2026-07-31T00:00:00Z', 'offline')
            """,
            (user_id,),
        )
        connection.commit()

    replace_user_food_access(
        db_path,
        user_id,
        ("food_a1b2c3d4e5f6", "food_112233445566"),
    )
    set_elfie_main_food_id(db_path, "12345678", "food_a1b2c3d4e5f6")

    assert list_user_food_access(db_path, user_id) == (
        "food_112233445566",
        "food_a1b2c3d4e5f6",
    )
    assert get_elfie_main_food_id(db_path, "12345678") == "food_a1b2c3d4e5f6"
    assert get_elfie_owner_user_id(db_path, "12345678") == user_id
