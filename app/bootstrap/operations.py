"""Production composition for system Operations."""

from __future__ import annotations

from app.features.operations import OperationsFacade
from infrastructure.models import RuntimeObserverProjectionAdapter
from infrastructure.persistence.operations import SQLiteOperationsAdapter


def build_operations_facade(db_path: str) -> OperationsFacade:
    persistence = SQLiteOperationsAdapter(db_path)
    return OperationsFacade(
        projection=persistence,
        maintenance=persistence,
        runtime_observer=RuntimeObserverProjectionAdapter(),
    )


__all__ = ("build_operations_facade",)
