"""Persistence contract for the resumable first-run Setup draft."""

from __future__ import annotations

from pathlib import Path

from app.features.setup.draft_repository import SetupDraftRepository
from app.infrastructure.persistence.final_schema import create_final_nest_database


def test_setup_draft_round_trips_without_returning_password_hash(tmp_path: Path) -> None:
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    repository = SetupDraftRepository(db_path)

    repository.save_owner(
        account_id="owner",
        display_name="First Owner",
        password_hash="pbkdf2_sha256$260000$salt$hash",
    )
    repository.save_offline(use_local_ollama=True, model_id="qwen2.5:0.5b")
    repository.save_nest(bed_count=8)

    draft = repository.get()
    assert draft.owner_account_id == "owner"
    assert draft.display_name == "First Owner"
    assert draft.password_hash == "pbkdf2_sha256$260000$salt$hash"
    assert draft.use_local_ollama is True
    assert draft.model_id == "qwen2.5:0.5b"
    assert draft.bed_count == 8
    assert draft.owner_configured is True
    assert draft.offline_configured is True
    assert draft.nest_configured is True
    assert draft.locked_at is None


def test_setup_draft_lock_is_idempotent(tmp_path: Path) -> None:
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    repository = SetupDraftRepository(db_path)

    repository.save_owner(
        account_id="owner",
        display_name=None,
        password_hash="pbkdf2_sha256$260000$salt$hash",
    )
    repository.save_offline(use_local_ollama=False, model_id=None)
    repository.save_nest(bed_count=4)
    assert repository.lock() is True
    assert repository.lock() is False
    assert repository.get().locked_at is not None
