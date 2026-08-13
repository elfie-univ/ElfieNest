"""Production composition for system Operations."""

from __future__ import annotations

from app.features.operations import OperationsFacade
from infrastructure.models.model_execution_observer import (
    ModelExecutionObserverProjectionAdapter,
)
from infrastructure.persistence.operations import SQLiteOperationsAdapter
from infrastructure.platform.mobile_network import PlatformMobileNetworkAdapter


def build_operations_facade(db_path: str) -> OperationsFacade:
    persistence = SQLiteOperationsAdapter(db_path)
    return OperationsFacade(
        projection=persistence,
        maintenance=persistence,
        model_execution_observer=ModelExecutionObserverProjectionAdapter(),
        network_access=PlatformMobileNetworkAdapter(),
    )


__all__ = ("build_operations_facade",)
