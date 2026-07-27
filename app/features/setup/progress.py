"""持久化的五步 Setup 进度；只保存状态和公开配置标识。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final, Tuple

from app.infrastructure.persistence.store import get_db

_SETUP_STEP_NAMES: Final[Tuple[str, ...]] = (
    "创建 Owner",
    "设备与离线保障",
    "精灵巢设置",
    "模型与粮食",
    "确认完成",
)
_OLLAMA_DECISIONS: Final[frozenset[str]] = frozenset(
    {"bound_existing", "install_official", "skipped"}
)
_MODEL_DECISIONS: Final[frozenset[str]] = frozenset({"configured", "skipped"})


@dataclass(frozen=True)
class SetupStep:
    number: int
    name: str
    status: str
    retry_action: str | None


@dataclass(frozen=True)
class SetupProgress:
    current_step: int
    complete: bool
    steps: Tuple[SetupStep, ...]
    last_error: str | None


@dataclass(frozen=True)
class SetupTask:
    """A non-secret, persisted status for one cancellable Setup activity."""

    step: int
    key: str
    state: str
    progress: int
    error: str | None


def get_setup_progress(db_path: str) -> SetupProgress:
    """Return progress and import a legacy Owner exactly once when needed."""
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_progress_row(conn)
        _reconcile_existing_owner(conn)
        row = _progress_row(conn)
        conn.commit()
    return _progress_from_row(row)


def complete_setup_step(
    db_path: str,
    *,
    step: int,
    decision: str | None = None,
    model_reference: str | None = None,
    ollama_endpoint: str | None = None,
) -> SetupProgress:
    """Commit one non-secret decision, idempotently and in wizard order."""
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_progress_row(conn)
        _reconcile_existing_owner(conn)
        row = _progress_row(conn)
        if _step_is_completed(row, step):
            conn.commit()
            return _progress_from_row(row)
        _require_current_step(row, step)
        if step == 2:
            _complete_ollama_step(conn, decision, ollama_endpoint)
        elif step == 3:
            _complete_nest_step(conn)
        elif step == 4:
            _complete_model_step(conn, decision, model_reference)
        elif step == 5:
            _complete_confirmation_step(conn, row)
        else:
            raise ValueError("只能通过 Owner 创建完成第一步")
        conn.commit()
    return get_setup_progress(db_path)


def record_setup_task_failure(
    db_path: str,
    *,
    step: int,
    task_key: str,
    error_message: str,
) -> None:
    """Record a retryable supported task failure without commands or credentials."""
    _require_supported_task(step, task_key)
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_progress_row(conn)
        _reconcile_existing_owner(conn)
        _require_current_step(_progress_row(conn), step)
        conn.execute(
            """
            UPDATE setup_progress
            SET current_step = ?, active_task_step = ?, active_task_key = ?,
                task_state = 'failed', task_progress = 0, last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1
            """,
            (step, step, task_key, _safe_error_message(error_message)),
        )
        conn.commit()


def begin_setup_task(db_path: str, *, step: int, task_key: str) -> SetupTask:
    """Reserve one supported Setup task before its background worker starts."""
    _require_supported_task(step, task_key)
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_progress_row(conn)
        _reconcile_existing_owner(conn)
        row = _progress_row(conn)
        _require_current_step(row, step)
        if row["task_state"] == "running":
            raise RuntimeError("当前 Setup 步骤已有进行中的任务")
        conn.execute(
            """
            UPDATE setup_progress
            SET active_task_step = ?, active_task_key = ?, task_state = 'running',
                task_progress = 1, last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1
            """,
            (step, task_key),
        )
        conn.commit()
    task = get_setup_task(db_path)
    if task is None:
        raise RuntimeError("Setup 任务状态写入失败")
    return task


def update_setup_task_progress(
    db_path: str,
    *,
    step: int,
    task_key: str,
    progress: int,
) -> None:
    """Advance a running task without exposing command output or credentials."""
    _require_supported_task(step, task_key)
    if progress < 1 or progress > 99:
        raise ValueError("Setup 任务进度必须在 1 到 99 之间")
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE setup_progress SET task_progress = ?, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1 AND active_task_step = ? AND active_task_key = ?
              AND task_state = 'running'
            """,
            (progress, step, task_key),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Setup 任务不再处于运行状态")
        conn.commit()


def cancel_setup_task(db_path: str, *, step: int, task_key: str) -> None:
    """Persist a cancellation request before a system installer begins."""
    _require_supported_task(step, task_key)
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE setup_progress
            SET task_state = 'cancelled', task_progress = 0,
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1 AND active_task_step = ? AND active_task_key = ?
              AND task_state = 'running'
            """,
            (step, task_key),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("没有可取消的 Setup 任务")
        conn.commit()


def get_setup_task(db_path: str) -> SetupTask | None:
    """Return the current unfinished task, if the wizard has one."""
    with get_db(db_path) as conn:
        _ensure_progress_row(conn)
        row = _progress_row(conn)
    if row["active_task_step"] is None or row["active_task_key"] is None:
        return None
    return SetupTask(
        step=int(row["active_task_step"]),
        key=str(row["active_task_key"]),
        state=str(row["task_state"]),
        progress=int(row["task_progress"]),
        error=str(row["last_error"]) if row["last_error"] else None,
    )


def recover_interrupted_setup_task(db_path: str) -> None:
    """Make an in-process task retryable after the host application restarts."""
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_progress_row(conn)
        cursor = conn.execute(
            """
            UPDATE setup_progress
            SET task_state = 'failed', task_progress = 0,
                last_error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1 AND task_state = 'running'
            """,
            ("应用重启前的 Setup 任务未完成；请确认后重试。",),
        )
        if cursor.rowcount > 0:
            conn.commit()
            return
        conn.commit()


def mark_owner_step_completed(conn: sqlite3.Connection, user_id: int) -> None:
    """Advance step 1 in the same transaction that creates the unique Owner."""
    _ensure_progress_row(conn)
    conn.execute(
        """
        UPDATE setup_progress
        SET owner_user_id = ?,
            owner_completed_at = COALESCE(owner_completed_at, CURRENT_TIMESTAMP),
            current_step = CASE WHEN current_step = 1 THEN 2 ELSE current_step END,
            updated_at = CURRENT_TIMESTAMP
        WHERE singleton_id = 1
        """,
        (user_id,),
    )


def _complete_ollama_step(
    conn: sqlite3.Connection,
    decision: str | None,
    endpoint: str | None,
) -> None:
    if decision not in _OLLAMA_DECISIONS:
        raise ValueError("Ollama 步骤需要明确选择")
    if decision != "skipped" and not endpoint:
        raise ValueError("Ollama 绑定必须保存固定 endpoint")
    _update_completed_step(
        conn,
        "ollama_decision = ?, ollama_endpoint = COALESCE(ollama_endpoint, ?)",
        (decision, endpoint),
        3,
    )


def _complete_nest_step(conn: sqlite3.Connection) -> None:
    _update_completed_step(
        conn,
        "nest_completed_at = COALESCE(nest_completed_at, CURRENT_TIMESTAMP)",
        (),
        4,
    )


def _complete_model_step(
    conn: sqlite3.Connection,
    decision: str | None,
    model_reference: str | None,
) -> None:
    if decision not in _MODEL_DECISIONS:
        raise ValueError("模型步骤需要明确选择或跳过")
    _update_completed_step(
        conn,
        "model_decision = ?, model_reference = ?",
        (decision, model_reference),
        5,
    )


def _complete_confirmation_step(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    if not all(state == "completed" for state in _step_states(row)[:4]):
        raise ValueError("前四步尚未完成，不能结束 Setup")
    _update_completed_step(
        conn,
        "completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)",
        (),
        5,
    )


def _update_completed_step(
    conn: sqlite3.Connection,
    assignment: str,
    values: Tuple[object, ...],
    next_step: int,
) -> None:
    conn.execute(
        f"""
        UPDATE setup_progress SET {assignment}, current_step = ?,
            active_task_step = NULL, active_task_key = NULL,
            task_state = 'completed', task_progress = 100,
            last_error = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE singleton_id = 1
        """,
        values + (next_step,),
    )


def _ensure_progress_row(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO setup_progress (singleton_id) VALUES (1)")


def _reconcile_existing_owner(conn: sqlite3.Connection) -> None:
    owner = conn.execute(
        "SELECT id FROM users WHERE role = 'owner' ORDER BY id LIMIT 1"
    ).fetchone()
    if owner is not None:
        mark_owner_step_completed(conn, int(owner[0]))


def _progress_row(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM setup_progress WHERE singleton_id = 1").fetchone()
    if row is None:
        raise RuntimeError("Setup 进度记录缺失")
    return row


def _step_is_completed(row: sqlite3.Row, step: int) -> bool:
    if step not in range(1, 6):
        raise ValueError("未知 Setup 步骤")
    return _step_states(row)[step - 1] == "completed"


def _require_current_step(row: sqlite3.Row, step: int) -> None:
    current = _first_incomplete_step(_step_states(row))
    if step != current:
        raise ValueError(f"请先完成第 {current} 步")


def _progress_from_row(row: sqlite3.Row) -> SetupProgress:
    states = _step_states(row)
    complete = row["completed_at"] is not None
    failed_step = int(row["active_task_step"] or 0)
    current_step = 5 if complete else _first_incomplete_step(states)
    if not complete and row["task_state"] == "failed" and failed_step in range(1, 6):
        current_step = failed_step
    return SetupProgress(
        current_step=current_step,
        complete=complete,
        steps=tuple(
            SetupStep(
                number=number,
                name=_SETUP_STEP_NAMES[number - 1],
                status=(
                    "failed"
                    if number == failed_step and row["task_state"] == "failed"
                    else states[number - 1]
                ),
                retry_action=_retry_action(number, row),
            )
            for number in range(1, 6)
        ),
        last_error=str(row["last_error"]) if row["last_error"] else None,
    )


def _step_states(row: sqlite3.Row) -> Tuple[str, ...]:
    return (
        "completed" if row["owner_user_id"] is not None else "pending",
        "completed" if row["ollama_decision"] is not None else "pending",
        "completed" if row["nest_completed_at"] is not None else "pending",
        "completed" if row["model_decision"] is not None else "pending",
        "completed" if row["completed_at"] is not None else "pending",
    )


def _first_incomplete_step(states: Tuple[str, ...]) -> int:
    for number, state in enumerate(states, start=1):
        if state != "completed":
            return number
    return 5


def _retry_action(step: int, row: sqlite3.Row) -> str | None:
    if row["task_state"] != "failed" or row["active_task_step"] != step:
        return None
    key = str(row["active_task_key"] or "")
    return f"retry_{key}" if key else None


def _require_supported_task(step: int, task_key: str) -> None:
    if (step, task_key) not in {(2, "ollama_install"), (4, "model_pull")}:
        raise ValueError("不支持的 Setup 长任务")


def _safe_error_message(message: str) -> str:
    if any(
        marker in message.lower()
        for marker in ("password", "token", "secret", "api key")
    ):
        return "敏感错误详情已隐藏；请在本机诊断日志中查看。"
    return message.strip()[:512] or "Setup 任务失败"
