"""Strict models crossing Operations outbound Ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .models import (
    ModelExecutionEventStatus,
    ModelExecutionEventType,
    ModelExecutionMetadataValue,
)


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
class StoredModelExecutionMetadata:
    key: str
    value: ModelExecutionMetadataValue


@dataclass(frozen=True)
class StoredModelExecutionEvent:
    event_type: ModelExecutionEventType
    status: ModelExecutionEventStatus
    subject: str
    metadata: Tuple[StoredModelExecutionMetadata, ...]


@dataclass(frozen=True)
class StoredModelExecutionSnapshot:
    event_count: int
    last_event: Optional[StoredModelExecutionEvent]


__all__ = (
    "StoredActiveSession",
    "StoredDatabaseBackup",
    "StoredModelExecutionEvent",
    "StoredModelExecutionMetadata",
    "StoredModelExecutionSnapshot",
    "StoredSpeciesCount",
    "StoredTableCount",
    "StoredUsageStats",
)
