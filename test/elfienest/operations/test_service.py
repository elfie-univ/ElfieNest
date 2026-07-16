from __future__ import annotations

from pathlib import Path

from elfienest.operations.service import (
    backup_database,
    collect_usage_stats,
    default_port_statuses,
    list_active_sessions,
    list_table_counts,
    reset_database,
    service_port_statuses,
)
from elfienest.persistence.store import get_db, init_db

from ..api._helpers import create_test_owner


def test_default_port_statuses_include_audio_server(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_check_port(port: int, name: str):
        calls.append((port, name))
        return None

    monkeypatch.setattr("elfienest.operations.service.check_port", fake_check_port)

    default_port_statuses()

    assert calls == [
        (8000, "HTTP 服务"),
        (8766, "WebSocket (管理)"),
        (8765, "WebSocket (Godot)"),
        (8767, "音频服务器"),
    ]


def test_service_port_statuses_uses_custom_http_and_ws_ports(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_check_port(port: int, name: str):
        calls.append((port, name))
        return None

    monkeypatch.setattr("elfienest.operations.service.check_port", fake_check_port)

    service_port_statuses(8100, 8866, 8768, 8769)

    assert calls == [
        (8100, "HTTP 服务"),
        (8866, "WebSocket (管理)"),
        (8768, "WebSocket (Godot)"),
        (8769, "音频服务器"),
    ]


def test_collect_usage_stats_reads_core_counts(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    owner_id = create_test_owner(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id, anatomy_type) "
            "VALUES (?, ?, ?, ?)",
            ("elfie_001", "小白", owner_id, "biped"),
        )
        conn.commit()

    stats = collect_usage_stats(db_path)

    assert stats.user_count == 1
    assert stats.owner_count == 1
    assert stats.owner_count == 1
    assert stats.elfie_count == 1
    assert stats.session_count == 0
    assert [(row.anatomy_type, row.count) for row in stats.anatomy_stats] == [
        ("biped", 1)
    ]


def test_list_active_sessions_uses_expires_at_schema(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    owner_id = create_test_owner(db_path, "owner")
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            ("abcdef123456", owner_id, 12345.0),
        )
        conn.commit()

    sessions = list_active_sessions(db_path)

    assert len(sessions) == 1
    assert sessions[0].token == "abcdef123456"
    assert sessions[0].username == "owner"
    assert sessions[0].expires_at == 12345.0


def test_list_table_counts_reports_existing_tables(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)

    counts = list_table_counts(db_path)

    count_by_name = {row.name: row.count for row in counts}
    assert count_by_name["users"] == 1
    assert "sessions" in count_by_name
    assert "elfie_registry" in count_by_name


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

    backup_path = backup_database(db_path)
    reset_database(db_path)

    assert backup_path.exists()
    assert not Path(db_path).exists()
