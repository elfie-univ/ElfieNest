"""Strict models crossing Operations outbound Ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .models import RuntimeEventStatus, RuntimeEventType, RuntimeMetadataValue


@dataclass(frozen=True)
class StoredSpeciesCount:
    species_id: str
    count: int


@dataclass(frozen=True)
class StoredUsageStats:
    user_count: int
    owner_count: int
    elfie_count: int
    session_count: int
    species_stats: Tuple[StoredSpeciesCount, ...]


@dataclass(frozen=True)
class StoredActiveSession:
    token_hash: str
    account_id: str
    expires_at: str


@dataclass(frozen=True)
class StoredTableCount:
    name: str
    count: int


@dataclass(frozen=True)
class StoredDatabaseBackup:
    backup_path: Path


@dataclass(frozen=True)
class StoredRuntimeMetadata:
    key: str
    value: RuntimeMetadataValue


@dataclass(frozen=True)
class StoredRuntimeEvent:
    event_type: RuntimeEventType
    status: RuntimeEventStatus
    subject: str
    metadata: Tuple[StoredRuntimeMetadata, ...]


@dataclass(frozen=True)
class StoredRuntimeSnapshot:
    event_count: int
    last_event: Optional[StoredRuntimeEvent]


__all__ = (
    "StoredActiveSession",
    "StoredDatabaseBackup",
    "StoredRuntimeEvent",
    "StoredRuntimeMetadata",
    "StoredRuntimeSnapshot",
    "StoredSpeciesCount",
    "StoredTableCount",
    "StoredUsageStats",
)
