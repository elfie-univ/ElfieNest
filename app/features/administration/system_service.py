from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ai_runtime.storage.data_home import get_db_path
from app.infrastructure.persistence.database_maintenance import (
    backup_final_databases,
    reset_final_databases,
)
from app.infrastructure.persistence.session_repository import SessionRepository
from app.infrastructure.persistence.store import get_db
from app.infrastructure.persistence.system_repository import SystemRepository


class DatabaseUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class PortStatus:
    port: int
    name: str
    running: bool


@dataclass(frozen=True)
class SpeciesCount:
    species_id: str
    count: int


@dataclass(frozen=True)
class UsageStats:
    user_count: int
    owner_count: int
    elfie_count: int
    session_count: int
    species_stats: List[SpeciesCount]


@dataclass(frozen=True)
class ActiveSession:
    token_hash: str
    account_id: str
    expires_at: str


@dataclass(frozen=True)
class TableCount:
    name: str
    count: int


def check_port(port: int, name: str, host: str = "127.0.0.1") -> PortStatus:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        running = sock.connect_ex((host, port)) == 0
    return PortStatus(port=port, name=name, running=running)


def default_port_statuses() -> List[PortStatus]:
    return service_port_statuses(8000, 8766)


def service_port_statuses(
    http_port: int,
    websocket_port: int,
    godot_ws_port: int = 8765,
) -> List[PortStatus]:
    return [
        check_port(http_port, "HTTP"),
        check_port(websocket_port, "WebSocket (admin)"),
        check_port(godot_ws_port, "WebSocket (Godot)"),
    ]


def collect_usage_stats(db_path: Optional[str] = None) -> UsageStats:
    database_path = _resolve_existing_db_path(db_path)
    with get_db(str(database_path)) as conn:
        repository = SystemRepository(conn)
        user_count, owner_count, elfie_count = repository.usage_counts()
        session_count = SessionRepository(conn).count_active(datetime.now(timezone.utc))
        species_stats = [
            SpeciesCount(species_id=species, count=count)
            for species, count in repository.species_counts()
        ]

    return UsageStats(
        user_count=user_count,
        owner_count=owner_count,
        elfie_count=elfie_count,
        session_count=session_count,
        species_stats=species_stats,
    )


def list_active_sessions(
    db_path: Optional[str] = None,
    limit: int = 20,
) -> List[ActiveSession]:
    database_path = _resolve_existing_db_path(db_path)
    with get_db(str(database_path)) as conn:
        return [
            ActiveSession(
                token_hash=row.token_hash,
                account_id=row.account_id,
                expires_at=row.expires_at,
            )
            for row in SessionRepository(conn).list_active(
                datetime.now(timezone.utc), limit
            )
        ]


def list_table_counts(db_path: Optional[str] = None) -> List[TableCount]:
    database_path = _resolve_existing_db_path(db_path)
    with get_db(str(database_path)) as conn:
        return [
            TableCount(name=name, count=count)
            for name, count in SystemRepository(conn).table_counts()
        ]


def backup_database(
    db_path: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> Path:
    database_path = _resolve_existing_db_path(db_path)
    return backup_final_databases(database_path, timestamp or datetime.now())


def reset_database(db_path: Optional[str] = None) -> None:
    database_path = _resolve_existing_db_path(db_path)
    reset_final_databases(database_path)


def _resolve_existing_db_path(db_path: Optional[str]) -> Path:
    database_path = Path(db_path) if db_path else get_db_path()
    if not database_path.exists():
        raise DatabaseUnavailableError(f"数据库不存在: {database_path}")
    return database_path
