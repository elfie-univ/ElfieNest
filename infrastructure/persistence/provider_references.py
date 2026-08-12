"""Read-only Food-reference protection for Provider administration."""

from __future__ import annotations

from app.features.configuration import ProviderPortError
from app.features.configuration.food import FoodPortError

from .food import list_food_model_references


class SQLiteProviderReferenceAdapter:
    """Expose only reference conflicts; never transfer Food ownership."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def connections_referenced_by_food(self, connection_id: str) -> tuple[str, ...]:
        try:
            return tuple(
                food_id
                for food_id, references in list_food_model_references(self._db_path)
                if any(
                    _connection_id(reference) == connection_id
                    for reference in references
                )
            )
        except FoodPortError as error:
            raise ProviderPortError("Unable to read Food references") from error

    def models_referenced_by_food(
        self,
        connection_id: str,
        model_id: str,
    ) -> tuple[str, ...]:
        try:
            target = f"{connection_id}/{model_id}"
            return tuple(
                food_id
                for food_id, references in list_food_model_references(self._db_path)
                if target in references
            )
        except FoodPortError as error:
            raise ProviderPortError("Unable to read Food references") from error


def _connection_id(reference: str) -> str:
    connection_id, separator, _ = reference.partition("/")
    return connection_id if separator else ""


__all__ = ("SQLiteProviderReferenceAdapter",)
