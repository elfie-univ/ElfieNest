from __future__ import annotations

from dataclasses import replace

import pytest

from app.features.configuration.food import (
    FoodPortConflict,
    FoodPortInvalid,
    StoredFoodPackage,
)
from infrastructure.persistence.food import (
    SQLiteFoodAdapter,
    list_food_model_references,
)
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)


def _seed_user_and_elfie(db_path: str) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id,account_id,password_hash,role) VALUES(7,'member','unused','user')"
        )
        connection.execute(
            """INSERT INTO elfies
               (elfie_id,owner_user_id,adopted_at,status)
               VALUES('00000001',7,'2026-08-01T00:00:00Z','offline')"""
        )
        connection.commit()


def test_adapter_round_trips_packages_assignments_and_provider_references(
    tmp_path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_user_and_elfie(db_path)
    adapter = SQLiteFoodAdapter(db_path)
    package = StoredFoodPackage(
        food_id="food_custom",
        display_name="Custom",
        enabled=True,
        primary_model="cloud/main",
        reasoning_model="cloud/reasoning",
        required_roles=frozenset({"reasoning", "vision"}),
        visibility_mode="users",
        visible_user_ids=(7,),
    )

    assert adapter.create_package(package) == package
    assert adapter.get_package("food_custom") == package
    runtime_package = adapter.load().packages["food_custom"]
    assert runtime_package.primary is not None
    assert runtime_package.primary.model == "cloud/main"
    assert list_food_model_references(db_path) == (
        ("food_common", ()),
        ("food_custom", ("cloud/main", "cloud/reasoning")),
        ("food_emergency", ()),
    )
    references = SQLiteProviderReferenceAdapter(db_path)
    assert references.connections_referenced_by_food("cloud") == ("food_custom",)
    assert references.models_referenced_by_food("cloud", "main") == ("food_custom",)

    assignment = adapter.get_assignment("00000001")
    assert assignment is not None and assignment.main_food_id is None
    adapter.set_main_food("00000001", "food_custom")
    updated_assignment = adapter.get_assignment("00000001")
    assert updated_assignment is not None
    assert updated_assignment.main_food_id == "food_custom"

    archived = replace(package, enabled=False, archived=True)
    adapter.update_package(archived)
    with pytest.raises(FoodPortConflict, match="still assigned"):
        adapter.delete_package("food_custom")


def test_adapter_rejects_unknown_visibility_user_and_unarchived_delete(
    tmp_path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteFoodAdapter(db_path)
    package = StoredFoodPackage(
        food_id="food_custom",
        display_name="Custom",
        visibility_mode="users",
        visible_user_ids=(404,),
    )
    with pytest.raises(FoodPortInvalid, match="do not exist"):
        adapter.create_package(package)

    valid = StoredFoodPackage(food_id="food_valid", display_name="Valid", enabled=False)
    adapter.create_package(valid)
    with pytest.raises(FoodPortConflict, match="Only archived"):
        adapter.delete_package("food_valid")
