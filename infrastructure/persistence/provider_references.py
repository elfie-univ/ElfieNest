"""Read-only Food-reference protection for Provider administration."""

from __future__ import annotations

import sqlite3

from ai_runtime.food.store import foods_referencing_connection, foods_referencing_model
from app.features.configuration import ProviderPortError
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository


class SQLiteProviderReferenceAdapter:
    """Expose only reference conflicts; never transfer Food ownership."""

    def __init__(self, db_path: str) -> None:
        self._repository = SQLiteFoodPackageRepository(db_path)

    def connections_referenced_by_food(self, connection_id: str) -> tuple[str, ...]:
        try:
            return tuple(
                foods_referencing_connection(self._repository.load(), connection_id)
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            raise ProviderPortError("Unable to read Food references") from error

    def models_referenced_by_food(
        self,
        connection_id: str,
        model_id: str,
    ) -> tuple[str, ...]:
        try:
            return tuple(
                foods_referencing_model(
                    self._repository.load(),
                    connection_id,
                    model_id,
                )
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            raise ProviderPortError("Unable to read Food references") from error


__all__ = ("SQLiteProviderReferenceAdapter",)
