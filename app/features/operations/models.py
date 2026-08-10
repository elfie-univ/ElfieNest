"""Commands, queries and results owned by Operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple, Union

RuntimeEventType = Literal[
    "model_call",
    "tool_call",
    "permission_decision",
    "fallback",
    "provider_verify",
    "food_decision",
]
RuntimeEventStatus = Literal["ok", "error"]
RuntimeMetadataValue = Union[str, int, float, bool]


@dataclass(frozen=True)
class GetUsageStatsQuery:
    pass


@dataclass(frozen=True)
class ListActiveSessionsQuery:
    limit: int = 20


@dataclass(frozen=True)
class ListTableCountsQuery:
    pass


@dataclass(frozen=True)
class BackupDatabasesCommand:
    pass


@dataclass(frozen=True)
class ResetDatabasesCommand:
    pass


@dataclass(frozen=True)
class GetRuntimeStatusQuery:
    pass


@dataclass(frozen=True)
class SpeciesCountResult:
    species_id: str
    count: int


@dataclass(frozen=True)
class UsageStatsResult:
    user_count: int
    owner_count: int
    elfie_count: int
    session_count: int
    species_stats: Tuple[SpeciesCountResult, ...]


@dataclass(frozen=True)
class ActiveSessionResult:
    token_hash: str
    account_id: str
    expires_at: str


@dataclass(frozen=True)
class ActiveSessionsResult:
    items: Tuple[ActiveSessionResult, ...]


@dataclass(frozen=True)
class TableCountResult:
    name: str
    count: int


@dataclass(frozen=True)
class TableCountsResult:
    items: Tuple[TableCountResult, ...]


@dataclass(frozen=True)
class DatabaseBackupResult:
    backup_path: Path


@dataclass(frozen=True)
class RuntimeMetadataEntry:
    key: str
    value: RuntimeMetadataValue


@dataclass(frozen=True)
class RuntimeEventResult:
    event_type: RuntimeEventType
    status: RuntimeEventStatus
    subject: str
    metadata: Tuple[RuntimeMetadataEntry, ...]


@dataclass(frozen=True)
class RuntimeObserverResult:
    event_count: int
    last_event: Optional[RuntimeEventResult]


@dataclass(frozen=True)
class RuntimeStatusResult:
    status: Literal["ok"]
    observer: RuntimeObserverResult


__all__ = (
    "ActiveSessionResult",
    "ActiveSessionsResult",
    "BackupDatabasesCommand",
    "DatabaseBackupResult",
    "GetRuntimeStatusQuery",
    "GetUsageStatsQuery",
    "ListActiveSessionsQuery",
    "ListTableCountsQuery",
    "ResetDatabasesCommand",
    "RuntimeEventResult",
    "RuntimeEventStatus",
    "RuntimeEventType",
    "RuntimeMetadataEntry",
    "RuntimeMetadataValue",
    "RuntimeObserverResult",
    "RuntimeStatusResult",
    "SpeciesCountResult",
    "TableCountResult",
    "TableCountsResult",
    "UsageStatsResult",
)
