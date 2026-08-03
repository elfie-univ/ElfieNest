"""Tests for one locked Setup installation task and its Owner handoff."""

from __future__ import annotations

from pathlib import Path

from app.features.setup.draft_repository import SetupDraftRepository
from app.features.setup.installer import SetupInstallJobManager
from app.features.setup.service import create_first_owner_from_hash
from app.infrastructure.persistence.final_schema import create_final_nest_database
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import get_db


def _complete_draft(db_path: str) -> None:
    draft = SetupDraftRepository(db_path)
    draft.save_owner(
        account_id="owner",
        display_name="Owner",
        password_hash="pbkdf2_sha256$260000$salt$hash",
    )
    draft.save_offline(use_local_ollama=False, model_id=None)
    draft.save_nest(bed_count=4)


def test_owner_is_created_from_saved_hash_idempotently(tmp_path: Path) -> None:
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _complete_draft(db_path)
    draft = SetupDraftRepository(db_path).get()

    first = create_first_owner_from_hash(db_path, draft)
    second = create_first_owner_from_hash(db_path, draft)

    assert first.user_id == second.user_id
    with get_db(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_install_job_manager_runs_once_and_reports_global_progress(tmp_path: Path) -> None:
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _complete_draft(db_path)
    draft = SetupDraftRepository(db_path).get()
    create_first_owner_from_hash(db_path, draft)
    assert SetupDraftRepository(db_path).lock() is True

    manager = SetupInstallJobManager()
    observed: list[int] = []

    def worker() -> None:
        repository = SetupInstallRepository(db_path)
        repository.update(phase=2, action_key="ollama.reuse", progress=30)
        observed.append(repository.get().task_progress)

    first = manager.start(db_path=db_path, worker=worker)
    second = manager.start(db_path=db_path, worker=worker)
    assert first.active_task_step == 2
    assert second.active_task_step == 2
    assert manager.join(db_path, timeout=2.0) is True
    assert observed == [30]
    assert SetupInstallRepository(db_path).get().task_state == "running"


def test_interrupted_install_becomes_retryable_without_unlocking_draft(
    tmp_path: Path,
) -> None:
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _complete_draft(db_path)
    draft = SetupDraftRepository(db_path).get()
    create_first_owner_from_hash(db_path, draft)
    SetupDraftRepository(db_path).lock()
    repository = SetupInstallRepository(db_path)
    repository.begin_or_resume()
    repository.fail("model.pull", "model download failed")
    assert repository.get().task_state == "failed"
    assert SetupDraftRepository(db_path).get().locked_at is not None
