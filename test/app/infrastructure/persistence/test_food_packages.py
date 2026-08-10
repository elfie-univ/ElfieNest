"""SQLite repository tests for the single food-packages fact source."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_runtime.food.models import FoodPackage, ModelAssignment
from app.infrastructure.persistence.food_packages import (
    FoodPackageRepositoryError,
    SQLiteFoodPackageRepository,
)
from infrastructure.persistence.store import get_db, init_db


def _insert_users(db_path: str, user_ids: tuple[int, ...]) -> None:
    with get_db(db_path) as connection:
        for user_id in user_ids:
            connection.execute(
                "INSERT INTO users(id,account_id,password_hash,role) VALUES(?,?,?,'user')",
                (user_id, f"user-{user_id}", "unused"),
            )
        connection.commit()


def _package(
    *,
    key: str = "food_custom",
    enabled: bool = False,
    visibility_mode: str = "global",
    visible_user_ids: tuple[int, ...] = (),
) -> FoodPackage:
    return FoodPackage(
        key=key,
        display_name="自定义粮",
        enabled=enabled,
        primary=ModelAssignment("cloud/main") if enabled else None,
        reasoning=ModelAssignment("cloud/reasoning"),
        vision=ModelAssignment("cloud/vision"),
        tool=ModelAssignment("cloud/tool"),
        fallback=ModelAssignment("cloud/fallback"),
        visibility_mode=visibility_mode,
        visible_user_ids=visible_user_ids,
    )


def test_repository_round_trips_all_roles_and_canonicalizes_users(
    tmp_path: Path,
) -> None:
    # Given: a fresh final DB and selected users in non-canonical order.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    _insert_users(db_path, (2, 5))
    repository = SQLiteFoodPackageRepository(db_path)

    # When: a package with every role and duplicate user IDs is written.
    repository.create(
        _package(
            enabled=True,
            visibility_mode="users",
            visible_user_ids=(5, 2, 5),
        )
    )

    # Then: all roles survive and user IDs are canonicalized.
    stored = repository.get("food_custom")
    assert stored is not None
    assert stored.model_references == (
        "cloud/main",
        "cloud/reasoning",
        "cloud/vision",
        "cloud/tool",
        "cloud/fallback",
    )
    assert stored.visible_user_ids == (2, 5)


@pytest.mark.parametrize(
    ("visibility_mode", "visible_user_ids"),
    [("global", (2,)), ("users", ())],
)
def test_food_model_rejects_invalid_visibility_without_mutating_existing_row(
    tmp_path: Path,
    visibility_mode: str,
    visible_user_ids: tuple[int, ...],
) -> None:
    # Given: an existing valid package.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    repository = SQLiteFoodPackageRepository(db_path)
    repository.create(_package())
    before = repository.get("food_custom")
    assert before is not None

    # When/Then: the model rejects invalid visibility before a repository write.
    with pytest.raises(ValueError):
        _package(
            visibility_mode=visibility_mode,
            visible_user_ids=visible_user_ids,
        )
    assert repository.get("food_custom") == before


def test_repository_rejects_unknown_selected_user(tmp_path: Path) -> None:
    # Given: a fresh DB with no selected user 404.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    repository = SQLiteFoodPackageRepository(db_path)

    # When/Then: users mode must reference existing users.
    with pytest.raises(FoodPackageRepositoryError, match="用户不存在"):
        repository.create(
            _package(visibility_mode="users", visible_user_ids=(404,))
        )


def test_system_seed_is_idempotent_and_does_not_overwrite_configured_fields(
    tmp_path: Path,
) -> None:
    # Given: a fresh DB initialized twice.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "UPDATE food_packages SET primary_model_ref=? WHERE food_key='food_common'",
            ("cloud/main",),
        )
        connection.commit()

    # When: initialization is repeated.
    init_db(db_path)

    # Then: exactly two system rows remain and configured references survive.
    repository = SQLiteFoodPackageRepository(db_path)
    packages = repository.list()
    assert [package.key for package in packages] == ["food_emergency", "food_common"]
    common = repository.get("food_common")
    assert common is not None
    assert common.primary == ModelAssignment("cloud/main")


def test_direct_sql_enforces_food_package_invariants(tmp_path: Path) -> None:
    # Given: a fresh schema with both system rows already seeded.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    # When/Then: every invalid direct SQL shape is rejected by SQLite itself.
    with get_db(db_path) as connection:
        invalid_rows = (
            ("bad-json", "Bad", "global", "not-json", None, 0, 0, None),
            ("global-users", "Bad", "global", "[2]", None, 0, 0, None),
            ("empty-users", "Bad", "users", "[]", None, 0, 0, None),
            ("enabled-no-primary", "Bad", "global", "[]", None, 1, 0, None),
            ("archived-enabled", "Bad", "global", "[]", "cloud/main", 1, 1, None),
            ("string-users", "Bad", "users", '["2"]', None, 0, 0, None),
            ("duplicate-users", "Bad", "users", "[2,2]", None, 0, 0, None),
            ("zero-user", "Bad", "users", "[0]", None, 0, 0, None),
            ("duplicate-common", "Bad", "global", "[]", None, 0, 0, "common"),
            ("archived-system", "Bad", "global", "[]", None, 0, 1, "emergency"),
        )
        for key, label, mode, user_ids, primary, enabled, archived, system_role in invalid_rows:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """INSERT INTO food_packages
                       (food_key,display_name,system_role,primary_model_ref,
                        visibility_mode,visible_user_ids_json,enabled,archived)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (key, label, system_role, primary, mode, user_ids, enabled, archived),
                )


def test_failed_update_leaves_original_row_unchanged(tmp_path: Path) -> None:
    # Given: a valid enabled package.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    repository = SQLiteFoodPackageRepository(db_path)
    repository.create(_package(enabled=True))
    before = repository.get("food_custom")
    assert before is not None

    # When: a database CHECK rejects an enabled package without a primary.
    invalid = FoodPackage(
        key="food_custom",
        display_name="自定义粮",
        enabled=True,
        primary=None,
    )
    with pytest.raises(sqlite3.IntegrityError):
        repository.update(invalid)

    # Then: the previous complete row remains unchanged.
    assert repository.get("food_custom") == before
