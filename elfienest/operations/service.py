from __future__ import annotations

import shutil
import socket
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from runtime.storage.data_home import get_db_path


class DatabaseUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class PortStatus:
    port: int
    name: str
    running: bool


@dataclass(frozen=True)
class AnatomyCount:
    anatomy_type: str
    count: int


@dataclass(frozen=True)
class UsageStats:
    user_count: int
    owner_count: int
    elfie_count: int
    session_count: int
    anatomy_stats: List[AnatomyCount]

    @property
    def admin_count(self) -> int:
        """兼容旧调用；当前统计语义为 Owner 数。"""
        return self.owner_count


@dataclass(frozen=True)
class ActiveSession:
    token: str
    username: str
    expires_at: float


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
    audio_port: int = 8767,
) -> List[PortStatus]:
    return [
        check_port(http_port, "HTTP 服务"),
        check_port(websocket_port, "WebSocket (管理)"),
        check_port(godot_ws_port, "WebSocket (Godot)"),
        check_port(audio_port, "音频服务器"),
    ]


def collect_usage_stats(db_path: Optional[str] = None) -> UsageStats:
    database_path = _resolve_existing_db_path(db_path)
    with sqlite3.connect(database_path) as conn:
        user_count = _count_rows(conn, "users")
        owner_count = _count_rows(conn, "users", "WHERE role='owner'")
        elfie_count = _count_rows(conn, "elfie_registry")
        session_count = _count_rows(conn, "sessions")
        cursor = conn.execute(
            """
            SELECT anatomy_type, COUNT(*)
            FROM elfie_registry
            GROUP BY anatomy_type
            """
        )
        anatomy_stats = [
            AnatomyCount(anatomy_type=str(row[0]), count=int(row[1]))
            for row in cursor.fetchall()
        ]

    return UsageStats(
        user_count=user_count,
        owner_count=owner_count,
        elfie_count=elfie_count,
        session_count=session_count,
        anatomy_stats=anatomy_stats,
    )


def list_active_sessions(
    db_path: Optional[str] = None,
    limit: int = 20,
) -> List[ActiveSession]:
    database_path = _resolve_existing_db_path(db_path)
    with sqlite3.connect(database_path) as conn:
        cursor = conn.execute(
            """
            SELECT s.token, u.username, s.expires_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            ORDER BY s.expires_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            ActiveSession(
                token=str(row[0]), username=str(row[1]), expires_at=float(row[2])
            )
            for row in cursor.fetchall()
        ]


def list_table_counts(db_path: Optional[str] = None) -> List[TableCount]:
    database_path = _resolve_existing_db_path(db_path)
    with sqlite3.connect(database_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [str(row[0]) for row in cursor.fetchall()]
        return [
            TableCount(name=table_name, count=_count_rows(conn, table_name))
            for table_name in table_names
        ]


def backup_database(
    db_path: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> Path:
    database_path = _resolve_existing_db_path(db_path)
    backup_time = timestamp or datetime.now()
    backup_path = database_path.with_name(
        f"{database_path.name}.backup.{backup_time.strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(str(database_path), str(backup_path))
    return backup_path


def reset_database(db_path: Optional[str] = None) -> None:
    database_path = _resolve_existing_db_path(db_path)
    database_path.unlink()


def _resolve_existing_db_path(db_path: Optional[str]) -> Path:
    database_path = Path(db_path) if db_path else get_db_path()
    if not database_path.exists():
        raise DatabaseUnavailableError(f"数据库不存在: {database_path}")
    return database_path


def _count_rows(
    conn: sqlite3.Connection,
    table_name: str,
    where_clause: str = "",
) -> int:
    cursor = conn.execute(
        f"SELECT COUNT(*) FROM {_quote_identifier(table_name)} {where_clause}"
    )
    return int(cursor.fetchone()[0])


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
