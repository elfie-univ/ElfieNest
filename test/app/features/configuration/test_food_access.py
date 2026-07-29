from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog
from app.features.configuration.food_access import resolve_elfie_food_key
from app.infrastructure.persistence.food_assignments import (
    replace_user_food_access,
    set_elfie_primary_food,
)
from app.infrastructure.persistence.store import get_db, init_db


def test_runtime_food_resolution_tracks_current_elfie_assignment(tmp_path):
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
    catalog = FoodCatalog(
        default_food="food_default",
        fallback_food="food_relief",
        recipes={
            key: FoodRecipe(
                key,
                key,
                "test",
                ExecutionProfile(f"ollama/{key}"),
            )
            for key in ("food_default", "food_custom", "food_relief")
        },
    )
    replace_user_food_access(db_path, user_id, ("food_custom",))

    assert resolve_elfie_food_key(db_path, "12345678", catalog) == "food_default"

    set_elfie_primary_food(db_path, "12345678", "food_custom")

    assert resolve_elfie_food_key(db_path, "12345678", catalog) == "food_custom"
