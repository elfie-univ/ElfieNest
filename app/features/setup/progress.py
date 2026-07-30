"""Five-step Setup projections backed by the installation repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping, Tuple

from app.infrastructure.persistence.installation_record import InstallationRecord
from app.infrastructure.persistence.installation_repository import (
    InstallationRepository,
)

_SETUP_STEP_NAMES: Final[Tuple[str, ...]] = (
    "创建 Owner",
    "设备与离线保障",
    "精灵巢设置",
    "模型与粮食",
    "确认完成",
)
_INTERRUPTED_TASK_ERROR: Final = "应用重启前的 Setup 任务未完成；请确认后重试。"


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
    record = InstallationRepository(db_path).get_progress()
    return _progress_from_record(record)


def complete_setup_step(
    db_path: str,
    *,
    step: int,
    decision: str | None = None,
    model_reference: str | None = None,
    ollama_endpoint: str | None = None,
    config_snapshot: Mapping[str, Any] | None = None,
) -> SetupProgress:
    """Commit one non-secret decision, idempotently and in wizard order."""
    record = InstallationRepository(db_path).complete_step(
        step=step,
        decision=decision,
        model_reference=model_reference,
        ollama_endpoint=ollama_endpoint,
        config_snapshot=config_snapshot,
    )
    return _progress_from_record(record)


def require_setup_step(db_path: str, step: int) -> None:
    """Validate step order before a service performs external side effects."""
    InstallationRepository(db_path).require_current_step(step)


def record_setup_task_failure(
    db_path: str,
    *,
    step: int,
    task_key: str,
    error_message: str,
) -> None:
    """Record a retryable supported task failure without secrets."""
    _require_supported_task(step, task_key)
    InstallationRepository(db_path).record_task_failure(
        step=step,
        task_key=task_key,
        error_message=_safe_error_message(error_message),
    )


def begin_setup_task(db_path: str, *, step: int, task_key: str) -> SetupTask:
    """Reserve one supported Setup task before its background worker starts."""
    _require_supported_task(step, task_key)
    record = InstallationRepository(db_path).begin_task(step=step, task_key=task_key)
    task = _task_from_record(record)
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
    InstallationRepository(db_path).update_task_progress(
        step=step,
        task_key=task_key,
        progress=progress,
    )


def cancel_setup_task(db_path: str, *, step: int, task_key: str) -> None:
    """Persist a cancellation request before a system installer begins."""
    _require_supported_task(step, task_key)
    InstallationRepository(db_path).cancel_task(step=step, task_key=task_key)


def get_setup_task(db_path: str) -> SetupTask | None:
    """Return the current unfinished task, if the wizard has one."""
    return _task_from_record(InstallationRepository(db_path).get_task())


def recover_interrupted_setup_task(db_path: str) -> None:
    """Make an in-process task retryable after the host application restarts."""
    InstallationRepository(db_path).recover_interrupted_task(
        error_message=_INTERRUPTED_TASK_ERROR
    )


def _progress_from_record(record: InstallationRecord) -> SetupProgress:
    states = _step_states(record)
    complete = record.completed_at is not None
    failed_step = record.active_task_step or 0
    current_step = 5 if complete else _first_incomplete_step(states)
    if not complete and record.task_state == "failed" and failed_step in range(1, 6):
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
                    if number == failed_step and record.task_state == "failed"
                    else states[number - 1]
                ),
                retry_action=_retry_action(number, record),
            )
            for number in range(1, 6)
        ),
        last_error=record.last_error,
    )


def _task_from_record(record: InstallationRecord) -> SetupTask | None:
    if record.active_task_step is None or record.active_task_key is None:
        return None
    return SetupTask(
        step=record.active_task_step,
        key=record.active_task_key,
        state=record.task_state,
        progress=record.task_progress,
        error=record.last_error,
    )


def _step_states(record: InstallationRecord) -> Tuple[str, ...]:
    ordered_steps = ("not_started", "owner", "providers", "nest", "food")
    completed_index = ordered_steps.index(record.setup_step)
    completed_count = 5 if record.setup_state == "completed" else completed_index
    return tuple(
        "completed" if number <= completed_count else "pending"
        for number in range(1, 6)
    )


def _first_incomplete_step(states: Tuple[str, ...]) -> int:
    for number, state in enumerate(states, start=1):
        if state != "completed":
            return number
    return 5


def _retry_action(
    step: int,
    record: InstallationRecord,
) -> str | None:
    if record.task_state != "failed" or record.active_task_step != step:
        return None
    return f"retry_{record.active_task_key}" if record.active_task_key else None


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
