from __future__ import annotations

from pathlib import Path

import pytest

from app.features.setup.progress import (
    begin_setup_task,
    cancel_setup_task,
    get_setup_task,
    recover_interrupted_setup_task,
)
from app.features.setup.service import (
    SetupAlreadyCompleteError,
    complete_setup_step,
    create_first_owner,
    create_first_owner_account,
    get_setup_progress,
    needs_setup,
    record_setup_task_failure,
)
from app.infrastructure.persistence.store import get_db, init_db, migrate_db_if_needed


def test_create_first_owner_account_does_not_create_session(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    account = create_first_owner_account(
        db_path, username="owner", password="secret123"
    )

    with get_db(db_path) as conn:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert account.username == "owner"
    assert account.role == "owner"
    assert session_count == 0


def test_create_first_owner_creates_login_session(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    setup_result = create_first_owner(db_path, username="owner", password="secret123")

    with get_db(db_path) as conn:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert setup_result.session_token
    assert setup_result.csrf_token
    assert session_count == 1


def test_owner_creation_advances_only_first_setup_step(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    create_first_owner(db_path, username="owner", password="secret123")

    progress = get_setup_progress(db_path)
    assert progress.current_step == 2
    assert progress.steps[0].status == "completed"
    assert progress.steps[1].status == "pending"
    assert not progress.complete
    assert needs_setup(db_path)


def test_failed_model_task_resumes_at_same_step_after_reopen(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    create_first_owner(db_path, username="owner", password="secret123")
    complete_setup_step(db_path, step=2, decision="skipped")
    complete_setup_step(db_path, step=3)
    record_setup_task_failure(
        db_path,
        step=4,
        task_key="model_pull",
        error_message="模型下载连接中断",
    )

    reopened = get_setup_progress(db_path)
    assert reopened.current_step == 4
    assert reopened.steps[3].status == "failed"
    assert reopened.steps[3].retry_action == "retry_model_pull"
    assert reopened.steps[0].status == "completed"
    assert "secret123" not in repr(reopened)


def test_ollama_install_task_persists_running_and_cancelled_state(
    tmp_path: Path,
) -> None:
    """Ollama 安装任务在重启后仍能报告状态，并可在启动前取消。"""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")

    begin_setup_task(db_path, step=2, task_key="ollama_install")

    running = get_setup_task(db_path)
    assert running is not None
    assert running.step == 2
    assert running.key == "ollama_install"
    assert running.state == "running"
    assert running.progress == 1

    cancel_setup_task(db_path, step=2, task_key="ollama_install")

    cancelled = get_setup_task(db_path)
    assert cancelled is not None
    assert cancelled.state == "cancelled"
    assert get_setup_progress(db_path).current_step == 2


def test_interrupted_setup_task_becomes_retryable_after_restart(tmp_path: Path) -> None:
    """进程中断不能把安装永久伪装成运行中。"""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    begin_setup_task(db_path, step=2, task_key="ollama_install")

    recover_interrupted_setup_task(db_path)

    task = get_setup_task(db_path)
    assert task is not None
    assert task.state == "failed"
    assert task.error == "应用重启前的 Setup 任务未完成；请确认后重试。"


def test_create_first_owner_account_rejects_existing_user(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner_account(db_path, username="owner", password="secret123")

    with pytest.raises(SetupAlreadyCompleteError):
        create_first_owner_account(db_path, username="other", password="secret123")


def test_existing_owner_migration_keeps_recorded_ollama_endpoint(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("legacy-owner", "not-a-real-password-hash"),
        )
        conn.execute(
            """
            UPDATE setup_progress
            SET ollama_endpoint = ?, ollama_decision = 'bound_existing'
            WHERE singleton_id = 1
            """,
            ("http://127.0.0.1:11434",),
        )
        conn.execute("PRAGMA user_version = 11")
        conn.commit()

    migrate_db_if_needed(db_path)
    migrate_db_if_needed(db_path)

    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT owner_user_id, ollama_endpoint, ollama_decision FROM setup_progress"
        ).fetchone()
    assert row is not None
    assert row["owner_user_id"] is not None
    assert row["ollama_endpoint"] == "http://127.0.0.1:11434"
    assert row["ollama_decision"] == "bound_existing"
