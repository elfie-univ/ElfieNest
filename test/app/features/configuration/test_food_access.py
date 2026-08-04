from types import SimpleNamespace

from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FoodPackage,
    ModelAssignment,
)
from app.features.configuration.food_access import resolve_elfie_food_key
from app.infrastructure.persistence.food_assignments import (
    set_elfie_main_food_id,
)
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from app.infrastructure.persistence.store import get_db, init_db


def test_runtime_food_resolution_tracks_current_elfie_assignment(tmp_path, monkeypatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    monkeypatch.setattr(
        "app.features.configuration.food_access.project_food_health",
        lambda package, evidence: SimpleNamespace(status="healthy"),
    )
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
    repository = SQLiteFoodPackageRepository(db_path)
    repository.update(
        FoodPackage(
            key=FOOD_COMMON_ID,
            display_name="常用粮",
            system_role="common",
            primary=ModelAssignment("ollama/common"),
        )
    )
    repository.create(
        FoodPackage(
            key="food_custom",
            display_name="自定义粮",
            primary=ModelAssignment("ollama/custom"),
            visibility_mode="users",
            visible_user_ids=(user_id,),
        )
    )
    catalog = repository.load()

    assert resolve_elfie_food_key(db_path, "12345678", catalog) == FOOD_COMMON_ID

    set_elfie_main_food_id(db_path, "12345678", "food_custom")

    assert resolve_elfie_food_key(db_path, "12345678", catalog) == "food_custom"
