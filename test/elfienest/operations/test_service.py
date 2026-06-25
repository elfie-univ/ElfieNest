from __future__ import annotations

from pathlib import Path

from elfienest.manage.store import get_db, init_db
from elfienest.operations.service import (
    backup_database,
    collect_usage_stats,
    list_active_sessions,
    list_table_counts,
    reset_database,
)

from ..manage._helpers import create_test_admin


def test_collect_usage_stats_reads_core_counts(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    admin_id = create_test_admin(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id, anatomy_type) "
            "VALUES (?, ?, ?, ?)",
            ("elfie_001", "小白", admin_id, "biped"),
        )
        conn.commit()

    stats = collect_usage_stats(db_path)

    assert stats.user_count == 1
    assert stats.admin_count == 1
    assert stats.elfie_count == 1
    assert stats.session_count == 0
    assert [(row.anatomy_type, row.count) for row in stats.anatomy_stats] == [
        ("biped", 1)
    ]


def test_list_active_sessions_uses_expires_at_schema(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    admin_id = create_test_admin(db_path, "admin")
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            ("abcdef123456", admin_id, 12345.0),
        )
        conn.commit()

    sessions = list_active_sessions(db_path)

    assert len(sessions) == 1
    assert sessions[0].token == "abcdef123456"
    assert sessions[0].username == "admin"
    assert sessions[0].expires_at == 12345.0


def test_list_table_counts_reports_existing_tables(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_admin(db_path)

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
