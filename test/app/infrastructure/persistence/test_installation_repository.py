from __future__ import annotations

from pathlib import Path

from app.infrastructure.persistence.installation_repository import (
    InstallationRepository,
)
from app.infrastructure.persistence.store import get_db, hash_password, init_db


def test_installation_repository_recovers_interrupted_task(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    repository = InstallationRepository(db_path)
    with get_db(db_path) as connection:
        owner_id = int(
            connection.execute(
                "INSERT INTO users (account_id,password_hash,role) VALUES (?,?,'owner')",
                ("owner", hash_password("secret123")),
            ).lastrowid
        )
        repository.mark_owner_completed(connection, owner_id)
        connection.commit()

    running = repository.begin_task(2, "ollama_install")
    repository.recover_interrupted_task("interrupted")
    reopened = repository.get_progress()

    assert running.task_state == "running"
    assert reopened.task_state == "failed"
    assert reopened.active_task_step == 2
    assert reopened.last_error == "interrupted"


def test_installation_repository_completes_five_steps_without_legacy_table(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    repository = InstallationRepository(db_path)
    with get_db(db_path) as connection:
        owner_id = int(
            connection.execute(
                "INSERT INTO users (account_id,password_hash,role) VALUES (?,?,'owner')",
                ("owner", hash_password("secret123")),
            ).lastrowid
        )
        repository.mark_owner_completed(connection, owner_id)
        connection.commit()

    repository.complete_step(2)
    repository.complete_step(3)
    repository.complete_step(4)
    completed = repository.complete_step(5)

    assert completed.setup_state == "completed"
    assert completed.completed_at is not None
    with get_db(db_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "local_installations" in tables
    assert "setup_progress" not in tables
