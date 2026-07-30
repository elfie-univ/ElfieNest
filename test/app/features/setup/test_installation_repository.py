"""Setup persistence ownership and transaction characterization tests."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.features.setup.progress import begin_setup_task, complete_setup_step
from app.infrastructure.persistence.store import get_db, init_db

PROJECT_ROOT = Path(__file__).parents[4]
_LEGACY_TABLE_ACCESS = re.compile(r"\b(?:FROM|UPDATE|INTO)\s+setup_progress\b")


def test_setup_progress_access_is_owned_by_installation_repository() -> None:
    # Given: every Setup layer named by Card 17 and the repository target.
    repository_path = (
        PROJECT_ROOT
        / "app"
        / "infrastructure"
        / "persistence"
        / "installation_repository.py"
    )
    cutover_path = repository_path.with_name("installation_storage_cutover.py")
    setup_paths = (
        PROJECT_ROOT / "app" / "features" / "setup" / "progress.py",
        PROJECT_ROOT / "app" / "features" / "setup" / "service.py",
        PROJECT_ROOT / "app" / "interfaces" / "api" / "setup_routes.py",
    )

    # When: source ownership is inspected.
    repository_source = repository_path.read_text(encoding="utf-8")
    cutover_source = cutover_path.read_text(encoding="utf-8")
    setup_sources = {path: path.read_text(encoding="utf-8") for path in setup_paths}

    # Then: runtime code freezes the legacy table and owns target write locking.
    assert "setup_progress" not in repository_source
    assert "setup_progress" in cutover_source
    assert "BEGIN IMMEDIATE" in repository_source
    assert "local_installations" in repository_source
    assert "UPDATE setup_progress" not in repository_source
    assert "UPDATE setup_progress" not in cutover_source
    assert all(
        not _LEGACY_TABLE_ACCESS.search(source) for source in setup_sources.values()
    )
    assert "app.features.setup.progress" not in setup_sources[setup_paths[2]]


def test_concurrent_task_start_persists_exactly_one_running_task(
    tmp_path: Path,
) -> None:
    # Given: step two is current and two callers are ready to start the same task.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("owner", "not-a-real-password-hash"),
        )
        connection.commit()
    barrier = Barrier(2)

    def start_task() -> str:
        barrier.wait()
        try:
            return begin_setup_task(
                db_path,
                step=2,
                task_key="ollama_install",
            ).state
        except RuntimeError:
            return "conflict"

    # When: both callers cross the start boundary concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda _index: start_task(), range(2)))

    # Then: one reservation commits and the conflicting start commits nothing.
    assert sorted(outcomes) == ["conflict", "running"]
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT task_state, task_progress FROM local_installations "
            "WHERE installation_id = 'local'"
        ).fetchone()
    assert row is not None
    assert tuple(row) == ("running", 1)


def test_illegal_step_rolls_back_owner_reconciliation(tmp_path: Path) -> None:
    # Given: a legacy Owner exists but setup_progress has not reconciled step one.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("legacy-owner", "not-a-real-password-hash"),
        )
        connection.commit()

    # When: a caller attempts to skip directly to step three.
    with pytest.raises(ValueError, match="请先完成第 2 步"):
        complete_setup_step(db_path, step=3)

    # Then: the cutover and reconciliation roll back with the illegal write.
    with get_db(db_path) as connection:
        legacy_row = connection.execute(
            "SELECT current_step, owner_user_id FROM setup_progress "
            "WHERE singleton_id = 1"
        ).fetchone()
        target_row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'local_installations'"
        ).fetchone()
    assert legacy_row is not None
    assert tuple(legacy_row) == (1, None)
    assert target_row is None
