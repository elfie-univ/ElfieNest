from app.infrastructure.persistence.food_assignments import (
    get_elfie_owner_user_id,
    get_elfie_primary_food,
    list_user_food_access,
    replace_user_food_access,
    set_elfie_primary_food,
)
from app.infrastructure.persistence.store import get_db, init_db


def test_food_assignments_store_only_stable_external_ids(tmp_path):
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES ('u', 'h', 'user')"
        )
        user_id = int(
            connection.execute("SELECT id FROM users WHERE username='u'").fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO elfie_registry (elfie_id, name, owner_user_id)
            VALUES ('12345678', 'Elfie', ?)
            """,
            (user_id,),
        )
        connection.commit()

    replace_user_food_access(
        db_path,
        user_id,
        ("food_a1b2c3d4e5f6", "food_112233445566"),
    )
    set_elfie_primary_food(db_path, "12345678", "food_a1b2c3d4e5f6")

    assert list_user_food_access(db_path, user_id) == (
        "food_112233445566",
        "food_a1b2c3d4e5f6",
    )
    assert get_elfie_primary_food(db_path, "12345678") == "food_a1b2c3d4e5f6"
    assert get_elfie_owner_user_id(db_path, "12345678") == user_id
