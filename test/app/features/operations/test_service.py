from __future__ import annotations

from pathlib import Path

import pytest

from app.features.accounts import AccountPrincipal, parse_account_role
from app.features.operations import (
    BackupDatabasesCommand,
    DatabaseMaintenanceRejected,
    GetRuntimeStatusQuery,
    GetUsageStatsQuery,
    ListActiveSessionsQuery,
    ListTableCountsQuery,
    OperationsFacade,
    OperationsForbidden,
    OperationsPortError,
    OperationsPortUnsafeTarget,
    OperationsUnavailable,
    ResetDatabasesCommand,
    StoredActiveSession,
    StoredDatabaseBackup,
    StoredRuntimeEvent,
    StoredRuntimeMetadata,
    StoredRuntimeSnapshot,
    StoredSpeciesCount,
    StoredTableCount,
    StoredUsageStats,
)


class MemoryOperationsAdapter:
    def __init__(self) -> None:
        self.reset_called = False
        self.failure: OperationsPortError | None = None

    def collect_usage_stats(self) -> StoredUsageStats:
        self._fail_if_configured()
        return StoredUsageStats(
            user_count=3,
            owner_count=1,
            elfie_count=2,
            session_count=1,
            species_stats=(StoredSpeciesCount(species_id="fox", count=2),),
        )

    def list_active_sessions(self, limit: int) -> tuple[StoredActiveSession, ...]:
        self._fail_if_configured()
        return (
            StoredActiveSession(
                token_hash="a" * 64,
                account_id="owner",
                expires_at="2099-01-01T00:00:00+00:00",
            ),
        )[:limit]

    def list_table_counts(self) -> tuple[StoredTableCount, ...]:
        self._fail_if_configured()
        return (StoredTableCount(name="users", count=3),)

    def backup_databases(self) -> StoredDatabaseBackup:
        self._fail_if_configured()
        return StoredDatabaseBackup(backup_path=Path("/safe/backup"))

    def reset_databases(self) -> None:
        self._fail_if_configured()
        self.reset_called = True

    def _fail_if_configured(self) -> None:
        if self.failure is not None:
            raise self.failure


class MemoryRuntimeObserver:
    def __init__(self) -> None:
        self.read_count = 0

    def snapshot(self) -> StoredRuntimeSnapshot:
        self.read_count += 1
        return StoredRuntimeSnapshot(
            event_count=2,
            last_event=StoredRuntimeEvent(
                event_type="fallback",
                status="ok",
                subject="local_fast",
                metadata=(
                    StoredRuntimeMetadata(key="reason", value="remote unavailable"),
                ),
            ),
        )


def _principal(role: str) -> AccountPrincipal:
    assert role in {"owner", "admin", "user"}
    return AccountPrincipal(
        user_id=1,
        account_id="actor",
        role=parse_account_role(role),
        default_landing_page="manage",
    )


def _facade() -> tuple[
    OperationsFacade, MemoryOperationsAdapter, MemoryRuntimeObserver
]:
    adapter = MemoryOperationsAdapter()
    observer = MemoryRuntimeObserver()
    return OperationsFacade(adapter, adapter, observer), adapter, observer


def test_facade_maps_existing_database_projections() -> None:
    facade, _, _ = _facade()

    usage = facade.get_usage_stats(GetUsageStatsQuery())
    sessions = facade.list_active_sessions(ListActiveSessionsQuery(limit=20))
    tables = facade.list_table_counts(ListTableCountsQuery())
    backup = facade.backup_databases(BackupDatabasesCommand())

    assert usage.user_count == 3
    assert usage.species_stats[0].species_id == "fox"
    assert sessions.items[0].account_id == "owner"
    assert tables.items[0].name == "users"
    assert backup.backup_path == Path("/safe/backup")


def test_reset_delegates_to_the_existing_maintenance_boundary() -> None:
    facade, adapter, _ = _facade()

    facade.reset_databases(ResetDatabasesCommand())

    assert adapter.reset_called is True


def test_port_failures_are_stable_operations_errors() -> None:
    facade, adapter, _ = _facade()
    adapter.failure = OperationsPortError("database unavailable")

    with pytest.raises(OperationsUnavailable):
        facade.get_usage_stats(GetUsageStatsQuery())

    adapter.failure = OperationsPortUnsafeTarget("unsafe target")
    with pytest.raises(DatabaseMaintenanceRejected):
        facade.reset_databases(ResetDatabasesCommand())


def test_runtime_status_requires_manager_before_reading_observer() -> None:
    facade, _, observer = _facade()

    with pytest.raises(OperationsForbidden):
        facade.get_runtime_status(_principal("user"), GetRuntimeStatusQuery())

    assert observer.read_count == 0


def test_runtime_status_is_a_read_only_typed_projection() -> None:
    facade, _, observer = _facade()

    result = facade.get_runtime_status(_principal("owner"), GetRuntimeStatusQuery())

    assert result.status == "ok"
    assert result.observer.event_count == 2
    assert result.observer.last_event is not None
    assert result.observer.last_event.subject == "local_fast"
    assert result.observer.last_event.metadata[0].key == "reason"
    assert observer.read_count == 1
