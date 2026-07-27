"""Tests for resumable, non-blocking Setup task execution."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from app.features.setup.jobs import OllamaInstallJobManager
from app.features.setup.progress import get_setup_progress, get_setup_task
from app.features.setup.service import create_first_owner
from app.infrastructure.persistence.store import init_db


def test_ollama_job_runs_in_background_and_persists_failure(tmp_path: Path) -> None:
    """A background failure leaves step two retryable rather than blocking HTTP."""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    entered = Event()
    release = Event()

    def failing_worker() -> None:
        entered.set()
        assert release.wait(timeout=2)
        raise RuntimeError("官方下载暂时不可用")

    manager = OllamaInstallJobManager()
    task = manager.start(db_path=db_path, worker=failing_worker)

    assert task.state == "running"
    assert entered.wait(timeout=2)
    assert get_setup_task(db_path) is not None

    release.set()
    assert manager.join(db_path, timeout=2)
    progress = get_setup_progress(db_path)
    failed = get_setup_task(db_path)
    assert progress.current_step == 2
    assert failed is not None
    assert failed.state == "failed"
    assert failed.error == "官方下载暂时不可用"
