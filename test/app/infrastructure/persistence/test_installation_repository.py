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

    assert running.task_status == "running"
    assert reopened.task_status == "failed"
    assert reopened.install_step == 2
    assert reopened.last_error == "interrupted"


def test_installation_repository_completes_five_steps_without_legacy_table(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    repository = InstallationRepository(db_path)

    # Step 1: Create owner
    with get_db(db_path) as connection:
        owner_id = int(
            connection.execute(
                "INSERT INTO users (account_id,password_hash,role) VALUES (?,?,'owner')",
                ("owner", hash_password("secret123")),
            ).lastrowid
        )
        repository.mark_owner_completed(connection, owner_id)
        connection.commit()

    # Verify adapter layer: setup_step should be "owner" after owner creation
    progress = repository.get_progress()
    assert progress.setup_step == "owner", f"Expected setup_step='owner', got '{progress.setup_step}'"

    # Step 2: Complete providers step
    progress = repository.complete_step(2)
    assert progress.setup_step == "providers", f"Expected setup_step='providers', got '{progress.setup_step}'"

    # Step 3: Complete nest step
    progress = repository.complete_step(3)
    assert progress.setup_step == "nest", f"Expected setup_step='nest', got '{progress.setup_step}'"

    # Step 4: Complete food step
    progress = repository.complete_step(4)
    assert progress.setup_step == "food", f"Expected setup_step='food', got '{progress.setup_step}'"

    # Step 5: Complete final step
    completed = repository.complete_step(5)
    assert completed.setup_step == "food", f"Expected setup_step='food', got '{completed.setup_step}'"

    # Verify final state
    assert completed.status == "completed"
    assert completed.setup_completed_at is not None

    # Verify adapter layer field mapping works correctly
    assert completed.install_step == 5

    with get_db(db_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "local_installations" in tables
    assert "setup_progress" not in tables
