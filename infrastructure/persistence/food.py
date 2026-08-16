"""SQLite Adapter for the single Food package and assignment fact source."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, cast

from app.features.configuration.food import (
    FoodPortConflict,
    FoodPortError,
    FoodPortInvalid,
    FoodPortNotFound,
    FoodSystemRole,
    FoodVisibilityMode,
    StoredElfieFoodAssignment,
    StoredFoodPackage,
)
from elfie.brain.reasoning.food_port import FoodAssignment, FoodCatalog, FoodPackage
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection


class SQLiteFoodAdapter:
    """Implement Food catalog and Elfie assignment Ports over ``nest.db``."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def load(self) -> FoodCatalog:
        """Load the read-only Food projection consumed by one Elfie's brain."""
        packages = {
            package.food_id: _elfie_package(package) for package in self.list_packages()
        }
        return FoodCatalog(packages=packages)

    def list_packages(self) -> tuple[StoredFoodPackage, ...]:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                rows = connection.execute(
                    f"""{_PACKAGE_SELECT}
                        ORDER BY CASE system_role
                            WHEN 'emergency' THEN 0
                            WHEN 'common' THEN 1
                            ELSE 2 END, food_key"""
                ).fetchall()
            return tuple(_package_from_row(row) for row in rows)
        except FoodPortInvalid:
            raise
        except (OSError, sqlite3.Error) as error:
            raise FoodPortError("Unable to read Food packages") from error

    def get_package(self, food_id: str) -> StoredFoodPackage | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    f"{_PACKAGE_SELECT} WHERE food_key=?",
                    (food_id,),
                ).fetchone()
            return None if row is None else _package_from_row(row)
        except FoodPortInvalid:
            raise
        except (OSError, sqlite3.Error) as error:
            raise FoodPortError("Unable to read Food package") from error

    def create_package(self, package: StoredFoodPackage) -> StoredFoodPackage:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                _validate_selected_users(connection, package.visible_user_ids)
                connection.execute(
                    """INSERT INTO food_packages
                       (food_key,display_name,system_role,primary_model_ref,
                       reasoning_model_ref,vision_model_ref,tool_model_ref,
                        fallback_model_ref,required_roles_json,visibility_mode,
                        visible_user_ids_json,
                        enabled,archived)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    _write_values(package),
                )
                connection.commit()
            stored = self.get_package(package.food_id)
            if stored is None:
                raise FoodPortError("Food package disappeared after creation")
            return stored
        except FoodPortError:
            raise
        except sqlite3.IntegrityError as error:
            raise FoodPortInvalid(
                "Food package violates storage constraints"
            ) from error
        except (OSError, sqlite3.Error) as error:
            raise FoodPortError("Unable to create Food package") from error

    def update_package(self, package: StoredFoodPackage) -> StoredFoodPackage:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                _validate_selected_users(connection, package.visible_user_ids)
                cursor = connection.execute(
                    """UPDATE food_packages
                       SET display_name=?,system_role=?,primary_model_ref=?,
                           reasoning_model_ref=?,vision_model_ref=?,tool_model_ref=?,
                           fallback_model_ref=?,required_roles_json=?,visibility_mode=?,
                           visible_user_ids_json=?,
                           enabled=?,archived=?
                       WHERE food_key=?""",
                    _write_values(package)[1:] + (package.food_id,),
                )
                if cursor.rowcount != 1:
                    raise FoodPortNotFound("Food package not found")
                connection.commit()
            stored = self.get_package(package.food_id)
            if stored is None:
                raise FoodPortError("Food package disappeared after update")
            return stored
        except FoodPortError:
            raise
        except sqlite3.IntegrityError as error:
            raise FoodPortInvalid(
                "Food package violates storage constraints"
            ) from error
        except (OSError, sqlite3.Error) as error:
            raise FoodPortError("Unable to update Food package") from error

    def delete_package(self, food_id: str) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT system_role,archived FROM food_packages WHERE food_key=?",
                    (food_id,),
                ).fetchone()
                if row is None:
                    raise FoodPortNotFound("Food package not found")
                if row["system_role"] is not None:
                    raise FoodPortConflict("System Food packages cannot be deleted")
                if not bool(row["archived"]):
                    raise FoodPortConflict("Only archived Food packages can be deleted")
                reference = connection.execute(
                    "SELECT 1 FROM elfies WHERE main_food_id=? LIMIT 1",
                    (food_id,),
                ).fetchone()
                if reference is not None:
                    raise FoodPortConflict("Food package is still assigned to an Elfie")
                connection.execute(
                    "DELETE FROM food_packages WHERE food_key=?",
                    (food_id,),
                )
                connection.commit()
        except FoodPortError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise FoodPortError("Unable to delete Food package") from error

    def get_assignment(self, elfie_id: str) -> StoredElfieFoodAssignment | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    """SELECT elfie_id,owner_user_id,main_food_id
                       FROM elfies WHERE elfie_id=?""",
                    (elfie_id,),
                ).fetchone()
            if row is None:
                return None
            return StoredElfieFoodAssignment(
                elfie_id=str(row["elfie_id"]),
                owner_user_id=int(row["owner_user_id"]),
                main_food_id=(
                    None if row["main_food_id"] is None else str(row["main_food_id"])
                ),
            )
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            raise FoodPortError("Unable to read Elfie Food assignment") from error

    def list_assignments(self) -> tuple[StoredElfieFoodAssignment, ...]:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                rows = connection.execute(
                    """SELECT elfie_id,owner_user_id,main_food_id
                       FROM elfies ORDER BY elfie_id"""
                ).fetchall()
            return tuple(
                StoredElfieFoodAssignment(
                    elfie_id=str(row["elfie_id"]),
                    owner_user_id=int(row["owner_user_id"]),
                    main_food_id=(
                        None
                        if row["main_food_id"] is None
                        else str(row["main_food_id"])
                    ),
                )
                for row in rows
            )
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            raise FoodPortError("Unable to list Elfie Food assignments") from error

    def set_main_food(self, elfie_id: str, food_id: str) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE elfies
                       SET main_food_id=?,updated_at=CURRENT_TIMESTAMP
                       WHERE elfie_id=?""",
                    (food_id, elfie_id),
                )
                if cursor.rowcount != 1:
                    raise FoodPortNotFound("Elfie not found")
                connection.commit()
        except FoodPortError:
            raise
        except sqlite3.IntegrityError as error:
            raise FoodPortInvalid("Main Food assignment is invalid") from error
        except (OSError, sqlite3.Error) as error:
            raise FoodPortError("Unable to update Elfie Food assignment") from error


def list_food_model_references(
    db_path: str | Path,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the one persisted reference projection used by Provider guards."""
    try:
        with app_sqlite_connection(db_path) as connection:
            rows = connection.execute(
                """SELECT food_key,primary_model_ref,reasoning_model_ref,
                          vision_model_ref,tool_model_ref,fallback_model_ref
                   FROM food_packages ORDER BY food_key"""
            ).fetchall()
        return tuple(
            (
                str(row["food_key"]),
                tuple(
                    str(reference)
                    for reference in (
                        row["primary_model_ref"],
                        row["reasoning_model_ref"],
                        row["vision_model_ref"],
                        row["tool_model_ref"],
                        row["fallback_model_ref"],
                    )
                    if reference is not None
                ),
            )
            for row in rows
        )
    except (OSError, sqlite3.Error) as error:
        raise FoodPortError("Unable to read Food model references") from error


_PACKAGE_SELECT = """SELECT food_key,display_name,system_role,primary_model_ref,
                             reasoning_model_ref,vision_model_ref,tool_model_ref,
                             fallback_model_ref,required_roles_json,visibility_mode,
                             visible_user_ids_json,
                             enabled,archived
                      FROM food_packages"""


def _write_values(package: StoredFoodPackage) -> tuple[str | int | None, ...]:
    return (
        package.food_id,
        package.display_name,
        package.system_role,
        package.primary_model,
        package.reasoning_model,
        package.vision_model,
        package.tool_model,
        package.fallback_model,
        json.dumps(sorted(package.required_roles), separators=(",", ":")),
        package.visibility_mode,
        json.dumps(package.visible_user_ids, separators=(",", ":")),
        int(package.enabled),
        int(package.archived),
    )


def _package_from_row(row: sqlite3.Row) -> StoredFoodPackage:
    try:
        system_role = row["system_role"]
        if system_role not in {None, "emergency", "common"}:
            raise FoodPortInvalid("Food system role is corrupt")
        visibility_mode = row["visibility_mode"]
        if visibility_mode not in {"global", "users"}:
            raise FoodPortInvalid("Food visibility is corrupt")
        return StoredFoodPackage(
            food_id=str(row["food_key"]),
            display_name=str(row["display_name"]),
            system_role=cast(Optional[FoodSystemRole], system_role),
            enabled=bool(row["enabled"]),
            archived=bool(row["archived"]),
            primary_model=_optional_text(row["primary_model_ref"]),
            reasoning_model=_optional_text(row["reasoning_model_ref"]),
            vision_model=_optional_text(row["vision_model_ref"]),
            tool_model=_optional_text(row["tool_model_ref"]),
            fallback_model=_optional_text(row["fallback_model_ref"]),
            required_roles=frozenset(
                _decode_required_roles(str(row["required_roles_json"]))
            ),
            visibility_mode=cast(FoodVisibilityMode, visibility_mode),
            visible_user_ids=_decode_user_ids(str(row["visible_user_ids_json"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise FoodPortInvalid("Food package record is corrupt") from error


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _elfie_package(package: StoredFoodPackage) -> FoodPackage:
    return FoodPackage(
        key=package.food_id,
        display_name=package.display_name,
        system_role=package.system_role,
        enabled=package.enabled,
        archived=package.archived,
        primary=_elfie_assignment(package.primary_model),
        reasoning=_elfie_assignment(package.reasoning_model),
        vision=_elfie_assignment(package.vision_model),
        tool=_elfie_assignment(package.tool_model),
        fallback=_elfie_assignment(package.fallback_model),
    )


def _elfie_assignment(reference: str | None) -> FoodAssignment | None:
    return None if reference is None else FoodAssignment(reference)


def _decode_user_ids(raw: str) -> tuple[int, ...]:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FoodPortInvalid("Food visible users are corrupt") from error
    if not isinstance(decoded, list) or any(
        not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0
        for user_id in decoded
    ):
        raise FoodPortInvalid("Food visible users are corrupt")
    normalized = tuple(sorted(set(decoded)))
    if len(normalized) != len(decoded):
        raise FoodPortInvalid("Food visible users are not canonical")
    return normalized


def _decode_required_roles(raw: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FoodPortInvalid("Food required roles are corrupt") from error
    allowed = {"reasoning", "vision", "tool"}
    if (
        not isinstance(decoded, list)
        or any(not isinstance(role, str) or role not in allowed for role in decoded)
        or len(set(decoded)) != len(decoded)
    ):
        raise FoodPortInvalid("Food required roles are corrupt")
    return tuple(sorted(decoded))


def _validate_selected_users(
    connection: sqlite3.Connection,
    user_ids: tuple[int, ...],
) -> None:
    if not user_ids:
        return
    placeholders = ",".join("?" for _ in user_ids)
    rows = connection.execute(
        f"SELECT id FROM users WHERE id IN ({placeholders})",
        user_ids,
    ).fetchall()
    existing = {int(row["id"]) for row in rows}
    missing = tuple(user_id for user_id in user_ids if user_id not in existing)
    if missing:
        raise FoodPortInvalid(
            "Visible users do not exist: " + ",".join(map(str, missing))
        )


__all__ = ("SQLiteFoodAdapter", "list_food_model_references")
