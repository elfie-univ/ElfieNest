from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.features.operations import (
    OperationsPortDatabaseMissing,
    OperationsPortUnsafeTarget,
    StoredSpeciesCount,
)
from infrastructure.persistence.operations import SQLiteOperationsAdapter
from infrastructure.persistence.store import get_db, init_db
from test.app.interfaces.api._helpers import create_test_owner


def test_adapter_reads_existing_usage_sessions_and_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "nest.db"
    init_db(str(db_path))
    owner_id = create_test_owner(str(db_path))
    token_hash = hashlib.sha256(b"raw-session-token").hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    with get_db(str(db_path)) as connection:
        connection.execute(
            """INSERT INTO elfies
               (elfie_id,name,owner_user_id,species,adopted_at,status)
               VALUES (?,?,?,?,CURRENT_TIMESTAMP,'offline')""",
            ("00000001", "小白", owner_id, "dog"),
        )
        connection.execute(
            "INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)",
            (token_hash, owner_id, expires_at.isoformat()),
        )
        connection.execute('CREATE TABLE "quoted table" (id INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO "quoted table" DEFAULT VALUES')
        connection.commit()

    adapter = SQLiteOperationsAdapter(str(db_path))
    usage = adapter.collect_usage_stats()
    sessions = adapter.list_active_sessions(20)
    table_counts = {item.name: item.count for item in adapter.list_table_counts()}

    assert usage.user_count == 1
    assert usage.owner_count == 1
    assert usage.elfie_count == 1
    assert usage.session_count == 1
    assert usage.species_stats == (StoredSpeciesCount(species_id="dog", count=1),)
    assert sessions[0].token_hash == token_hash
    assert sessions[0].account_id == "owner"
    assert sessions[0].expires_at == expires_at.isoformat()
    assert table_counts["users"] == 1
    assert table_counts["quoted table"] == 1


def test_adapter_backups_and_resets_the_existing_final_databases(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "selected-home" / "nest.db"
    db_path.parent.mkdir()
    init_db(str(db_path))
    history_path = (
        db_path.parent / "elfies" / "00000001" / "conversations" / "history.sqlite"
    )
    knowledge_path = (
        db_path.parent / "elfies" / "00000001" / "memory" / "knowledge.sqlite"
    )
    history_path.parent.mkdir(parents=True)
    knowledge_path.parent.mkdir(parents=True)
    with sqlite3.connect(history_path) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('history')")
    with sqlite3.connect(knowledge_path) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('knowledge')")

    adapter = SQLiteOperationsAdapter(str(db_path))
    backup = adapter.backup_databases()
    adapter.reset_databases()

    assert (backup.backup_path / "nest.db").exists()
    with sqlite3.connect(
        backup.backup_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    ) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == "history"
    assert not db_path.exists()
    assert not history_path.exists()
    assert not knowledge_path.exists()


def test_adapter_rejects_missing_and_default_production_database_targets(
    tmp_path: Path,
) -> None:
    missing = SQLiteOperationsAdapter(str(tmp_path / "missing" / "nest.db"))
    with pytest.raises(OperationsPortDatabaseMissing):
        missing.collect_usage_stats()

    with pytest.raises(OperationsPortUnsafeTarget):
        SQLiteOperationsAdapter._validate_reset_target(
            Path.home() / ".elfienest" / "nest.db"
        )
