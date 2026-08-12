"""Consumer-owned technical boundaries required by Operations."""

from __future__ import annotations

from typing import Protocol, Tuple

from .port_models import (
    StoredActiveSession,
    StoredDatabaseBackup,
    StoredRuntimeSnapshot,
    StoredTableCount,
    StoredUsageStats,
)


class OperationsPortError(RuntimeError):
    """An Operations technical boundary could not complete an operation."""


class OperationsPortDatabaseMissing(OperationsPortError):
    """The selected application database does not exist."""


class OperationsPortUnsafeTarget(OperationsPortError):
    """The selected destructive target violates the existing safety policy."""


class OperationsProjectionPort(Protocol):
    def collect_usage_stats(self) -> StoredUsageStats: ...

    def list_active_sessions(self, limit: int) -> Tuple[StoredActiveSession, ...]: ...

    def list_table_counts(self) -> Tuple[StoredTableCount, ...]: ...


class DatabaseMaintenancePort(Protocol):
    def backup_databases(self) -> StoredDatabaseBackup: ...

    def reset_databases(self) -> None: ...


class RuntimeObserverProjectionPort(Protocol):
    def snapshot(self) -> StoredRuntimeSnapshot: ...


class NetworkAccessProjectionPort(Protocol):
    def preferred_lan_address(self) -> str | None: ...

    def current_wifi_name(self) -> str | None: ...


__all__ = (
    "DatabaseMaintenancePort",
    "NetworkAccessProjectionPort",
    "OperationsPortDatabaseMissing",
    "OperationsPortError",
    "OperationsPortUnsafeTarget",
    "OperationsProjectionPort",
    "RuntimeObserverProjectionPort",
)
