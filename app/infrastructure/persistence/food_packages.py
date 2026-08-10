"""SQLite persistence for the single ``food_packages`` fact source."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from ai_runtime.food.models import FoodPackage, ModelAssignment
from ai_runtime.food.store import FoodCatalog, FoodCatalogRepository
from infrastructure.persistence.store import get_db


class FoodPackageRepositoryError(RuntimeError):
    """Raised when a food package cannot satisfy the database contract."""


class SQLiteFoodPackageRepository(FoodCatalogRepository):
    """Own all SQL reads and writes for ``nest.db.food_packages``."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def load(self) -> FoodCatalog:
        """Load the complete database-backed catalog projection."""
        packages = {package.key: package for package in self.list()}
        return FoodCatalog(packages=packages)

    def list(self) -> tuple[FoodPackage, ...]:
        """Return system foods first, followed by custom foods by key."""
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                """SELECT food_key,display_name,system_role,primary_model_ref,
                          reasoning_model_ref,vision_model_ref,tool_model_ref,
                          fallback_model_ref,visibility_mode,visible_user_ids_json,
                          enabled,archived
                   FROM food_packages
                   ORDER BY CASE food_key
                       WHEN 'food_emergency' THEN 0
                       WHEN 'food_common' THEN 1
                       ELSE 2 END, food_key"""
            ).fetchall()
        return tuple(_package_from_row(row) for row in rows)

    def get(self, food_key: str) -> FoodPackage | None:
        """Return one package by its stable key."""
        with get_db(self._db_path) as connection:
            row = connection.execute(
                """SELECT food_key,display_name,system_role,primary_model_ref,
                          reasoning_model_ref,vision_model_ref,tool_model_ref,
                          fallback_model_ref,visibility_mode,visible_user_ids_json,
                          enabled,archived
                   FROM food_packages WHERE food_key=?""",
                (food_key,),
            ).fetchone()
        return None if row is None else _package_from_row(row)

    def create(self, package: FoodPackage) -> FoodPackage:
        """Insert one complete package in a single immediate transaction."""
        normalized = self._normalize_for_write(package)
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _validate_selected_users(connection, normalized.visible_user_ids)
            connection.execute(
                """INSERT INTO food_packages
                   (food_key,display_name,system_role,primary_model_ref,
                    reasoning_model_ref,vision_model_ref,tool_model_ref,
                    fallback_model_ref,visibility_mode,visible_user_ids_json,
                    enabled,archived)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                _write_values(normalized),
            )
            connection.commit()
        stored = self.get(normalized.key)
        if stored is None:
            raise FoodPackageRepositoryError("粮食写入后无法重新读取")
        return stored

    def update(self, package: FoodPackage) -> FoodPackage:
        """Replace one complete package in a single immediate transaction."""
        normalized = self._normalize_for_write(package)
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _validate_selected_users(connection, normalized.visible_user_ids)
            cursor = connection.execute(
                """UPDATE food_packages
                   SET display_name=?,system_role=?,primary_model_ref=?,
                       reasoning_model_ref=?,vision_model_ref=?,tool_model_ref=?,
                       fallback_model_ref=?,visibility_mode=?,visible_user_ids_json=?,
                       enabled=?,archived=?
                   WHERE food_key=?""",
                _write_values(normalized)[1:] + (normalized.key,),
            )
            if cursor.rowcount != 1:
                raise FoodPackageRepositoryError(f"粮食不存在: {normalized.key}")
            connection.commit()
        stored = self.get(normalized.key)
        if stored is None:
            raise FoodPackageRepositoryError("粮食更新后无法重新读取")
        return stored

    def delete(self, food_key: str) -> None:
        """Delete an archived custom package with main-food reference protection."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT system_role,archived FROM food_packages WHERE food_key=?",
                (food_key,),
            ).fetchone()
            if row is None:
                raise FoodPackageRepositoryError(f"粮食不存在: {food_key}")
            if row["system_role"] is not None:
                raise FoodPackageRepositoryError("系统粮食不能删除")
            if not bool(row["archived"]):
                raise FoodPackageRepositoryError("只能删除已归档粮食")
            reference = connection.execute(
                "SELECT 1 FROM elfies WHERE main_food_id=? LIMIT 1",
                (food_key,),
            ).fetchone()
            if reference is not None:
                raise FoodPackageRepositoryError("粮食仍被精灵引用")
            connection.execute("DELETE FROM food_packages WHERE food_key=?", (food_key,))
            connection.commit()

    @staticmethod
    def _normalize_for_write(package: FoodPackage) -> FoodPackage:
        """Normalize user IDs before crossing into SQLite."""
        normalized_ids = tuple(sorted(set(package.visible_user_ids)))
        if package.visibility_mode == "global" and normalized_ids:
            raise FoodPackageRepositoryError("全局可见不能包含用户")
        if package.visibility_mode == "users" and not normalized_ids:
            raise FoodPackageRepositoryError("指定用户可见至少需要一个用户")
        return replace(package, visible_user_ids=normalized_ids)


def _write_values(package: FoodPackage) -> tuple[str | int | None, ...]:
    return (
        package.key,
        package.display_name,
        package.system_role,
        _model_value(package.primary),
        _model_value(package.reasoning),
        _model_value(package.vision),
        _model_value(package.tool),
        _model_value(package.fallback),
        package.visibility_mode,
        json.dumps(package.visible_user_ids, separators=(",", ":")),
        int(package.enabled),
        int(package.archived),
    )


def _model_value(assignment: ModelAssignment | None) -> str | None:
    return None if assignment is None else assignment.model


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
        raise FoodPackageRepositoryError(f"用户不存在: {','.join(map(str, missing))}")


def _package_from_row(row: sqlite3.Row) -> FoodPackage:
    return FoodPackage(
        key=str(row["food_key"]),
        display_name=str(row["display_name"]),
        system_role=None if row["system_role"] is None else str(row["system_role"]),
        enabled=bool(row["enabled"]),
        archived=bool(row["archived"]),
        visibility_mode=str(row["visibility_mode"]),
        visible_user_ids=_decode_user_ids(str(row["visible_user_ids_json"])),
        primary=ModelAssignment.from_value(row["primary_model_ref"]),
        reasoning=ModelAssignment.from_value(row["reasoning_model_ref"]),
        vision=ModelAssignment.from_value(row["vision_model_ref"]),
        tool=ModelAssignment.from_value(row["tool_model_ref"]),
        fallback=ModelAssignment.from_value(row["fallback_model_ref"]),
    )


def _decode_user_ids(raw: str) -> tuple[int, ...]:
    decoded = json.loads(raw)
    if not isinstance(decoded, list) or any(
        not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0
        for user_id in decoded
    ):
        raise FoodPackageRepositoryError("粮食可见用户数据损坏")
    return tuple(sorted(set(decoded)))


__all__ = (
    "FoodPackageRepositoryError",
    "SQLiteFoodPackageRepository",
)
