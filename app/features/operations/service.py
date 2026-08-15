"""Existing system maintenance and management projections."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal, is_manager

from .errors import (
    DatabaseMaintenanceRejected,
    OperationsForbidden,
    OperationsUnavailable,
)
from .models import (
    ActiveSessionResult,
    ActiveSessionsResult,
    BackupDatabasesCommand,
    DatabaseBackupResult,
    GetMobileAccessQuery,
    GetRuntimeStatusQuery,
    GetUsageStatsQuery,
    ListActiveSessionsQuery,
    ListTableCountsQuery,
    MobileAccessResult,
    ModelExecutionEventResult,
    ModelExecutionMetadataEntry,
    ModelExecutionObserverResult,
    ResetDatabasesCommand,
    RuntimeStatusResult,
    SpeciesCountResult,
    TableCountResult,
    TableCountsResult,
    UsageStatsResult,
)
from .port_models import StoredModelExecutionEvent
from .ports import (
    DatabaseMaintenancePort,
    ModelExecutionObserverProjectionPort,
    NetworkAccessProjectionPort,
    OperationsPortError,
    OperationsPortUnsafeTarget,
    OperationsProjectionPort,
)


class OperationsFacade:
    def __init__(
        self,
        projection: OperationsProjectionPort,
        maintenance: DatabaseMaintenancePort,
        model_execution_observer: ModelExecutionObserverProjectionPort,
        network_access: NetworkAccessProjectionPort,
    ) -> None:
        self._projection = projection
        self._maintenance = maintenance
        self._model_execution_observer = model_execution_observer
        self._network_access = network_access

    def get_mobile_access(self, query: GetMobileAccessQuery) -> MobileAccessResult:
        try:
            address = self._network_access.preferred_lan_address()
            network_name = self._network_access.current_wifi_name()
        except OperationsPortError as error:
            raise OperationsUnavailable(str(error)) from error
        return MobileAccessResult(
            urls=(f"http://{address}:{query.http_port}",) if address else (),
            network_name=network_name,
        )

    def get_usage_stats(self, query: GetUsageStatsQuery) -> UsageStatsResult:
        _ = query
        try:
            stored = self._projection.collect_usage_stats()
        except OperationsPortError as error:
            raise OperationsUnavailable(str(error)) from error
        return UsageStatsResult(
            user_count=stored.user_count,
            owner_count=stored.owner_count,
            elfie_count=stored.elfie_count,
            session_count=stored.session_count,
            species_stats=tuple(
                SpeciesCountResult(species_id=item.species_id, count=item.count)
                for item in stored.species_stats
            ),
        )

    def list_active_sessions(
        self, query: ListActiveSessionsQuery
    ) -> ActiveSessionsResult:
        try:
            stored = self._projection.list_active_sessions(query.limit)
        except OperationsPortError as error:
            raise OperationsUnavailable(str(error)) from error
        return ActiveSessionsResult(
            items=tuple(
                ActiveSessionResult(
                    token_hash=item.token_hash,
                    account_id=item.account_id,
                    expires_at=item.expires_at,
                )
                for item in stored
            )
        )

    def list_table_counts(self, query: ListTableCountsQuery) -> TableCountsResult:
        _ = query
        try:
            stored = self._projection.list_table_counts()
        except OperationsPortError as error:
            raise OperationsUnavailable(str(error)) from error
        return TableCountsResult(
            items=tuple(
                TableCountResult(name=item.name, count=item.count) for item in stored
            )
        )

    def backup_databases(self, command: BackupDatabasesCommand) -> DatabaseBackupResult:
        _ = command
        try:
            stored = self._maintenance.backup_databases()
        except OperationsPortError as error:
            raise OperationsUnavailable(str(error)) from error
        return DatabaseBackupResult(backup_path=stored.backup_path)

    def reset_databases(self, command: ResetDatabasesCommand) -> None:
        _ = command
        try:
            self._maintenance.reset_databases()
        except OperationsPortUnsafeTarget as error:
            raise DatabaseMaintenanceRejected(str(error)) from error
        except OperationsPortError as error:
            raise OperationsUnavailable(str(error)) from error

    def get_runtime_status(
        self,
        principal: AccountPrincipal,
        query: GetRuntimeStatusQuery,
    ) -> RuntimeStatusResult:
        _ = query
        if not is_manager(principal.role):
            raise OperationsForbidden("Runtime status requires a manager")
        try:
            snapshot = self._model_execution_observer.snapshot()
        except OperationsPortError as error:
            raise OperationsUnavailable(str(error)) from error
        return RuntimeStatusResult(
            status="ok",
            observer=ModelExecutionObserverResult(
                event_count=snapshot.event_count,
                last_event=(
                    None
                    if snapshot.last_event is None
                    else self._event_result(snapshot.last_event)
                ),
            ),
        )

    @staticmethod
    def _event_result(event: StoredModelExecutionEvent) -> ModelExecutionEventResult:
        return ModelExecutionEventResult(
            event_type=event.event_type,
            status=event.status,
            subject=event.subject,
            metadata=tuple(
                ModelExecutionMetadataEntry(key=item.key, value=item.value)
                for item in event.metadata
            ),
        )


__all__ = ("OperationsFacade",)
