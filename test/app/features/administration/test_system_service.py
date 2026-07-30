from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.features.administration.system_service import (
    backup_database,
    collect_usage_stats,
    default_port_statuses,
    list_active_sessions,
    list_table_counts,
    reset_database,
    service_port_statuses,
)
from app.infrastructure.persistence.store import get_db, init_db
from test.app.interfaces.api._helpers import create_test_owner


def test_default_port_statuses_include_application_services(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_check_port(port: int, name: str):
        calls.append((port, name))
        return None

    monkeypatch.setattr(
        "app.features.administration.system_service.check_port", fake_check_port
    )

    default_port_statuses()

    assert calls == [
        (8000, "HTTP"),
        (8766, "WebSocket (admin)"),
        (8765, "WebSocket (Godot)"),
    ]


def test_service_port_statuses_uses_custom_http_and_ws_ports(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_check_port(port: int, name: str):
        calls.append((port, name))
        return None

    monkeypatch.setattr(
        "app.features.administration.system_service.check_port", fake_check_port
    )

    service_port_statuses(8100, 8866, 8768)

    assert calls == [
        (8100, "HTTP"),
        (8866, "WebSocket (admin)"),
        (8768, "WebSocket (Godot)"),
    ]


def test_collect_usage_stats_reads_core_counts(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    owner_id = create_test_owner(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO elfies "
            "(elfie_id, name, owner_user_id, species, adopted_at, status) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'offline')",
            ("00000001", "小白", owner_id, "dog"),
        )
        conn.commit()

    stats = collect_usage_stats(db_path)

    assert stats.user_count == 1
    assert stats.owner_count == 1
    assert stats.owner_count == 1
    assert stats.elfie_count == 1
    assert stats.session_count == 0
    assert [(row.species_id, row.count) for row in stats.species_stats] == [("dog", 1)]


def test_list_active_sessions_uses_expires_at_schema(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    owner_id = create_test_owner(db_path, "owner")
    token_hash = hashlib.sha256(b"raw-session-token").hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, owner_id, expires_at.isoformat()),
        )
        conn.commit()

    sessions = list_active_sessions(db_path)

    assert len(sessions) == 1
    assert sessions[0].token_hash == token_hash
    assert sessions[0].username == "owner"
    assert sessions[0].expires_at == expires_at.isoformat()


def test_list_table_counts_reports_existing_tables(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)

    counts = list_table_counts(db_path)

    count_by_name = {row.name: row.count for row in counts}
    assert count_by_name["users"] == 1
    assert "sessions" in count_by_name
    assert "elfies" in count_by_name


def test_list_table_counts_handles_quoted_table_names(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as conn:
        conn.execute('CREATE TABLE "quoted table" (id INTEGER PRIMARY KEY)')
        conn.execute('INSERT INTO "quoted table" DEFAULT VALUES')
        conn.commit()

    counts = list_table_counts(db_path)

    count_by_name = {row.name: row.count for row in counts}
    assert count_by_name["quoted table"] == 1


def test_backup_and_reset_database(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    history_path = tmp_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    knowledge_path = tmp_path / "elfies" / "00000001" / "memory" / "knowledge.sqlite"
    history_path.parent.mkdir(parents=True)
    knowledge_path.parent.mkdir(parents=True)
    with sqlite3.connect(history_path) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('history')")
    with sqlite3.connect(knowledge_path) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('knowledge')")

    backup_path = backup_database(db_path)
    reset_database(db_path)

    assert backup_path.exists()
    assert (backup_path / "nest.db").exists()
    backup_history = (
        backup_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    )
    backup_knowledge = (
        backup_path / "elfies" / "00000001" / "memory" / "knowledge.sqlite"
    )
    with sqlite3.connect(backup_history) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == "history"
    with sqlite3.connect(backup_knowledge) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == "knowledge"
    assert not Path(db_path).exists()
    assert not history_path.exists()
    assert not knowledge_path.exists()
