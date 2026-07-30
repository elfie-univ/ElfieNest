"""Five-step Setup projections backed only by ``local_installations``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Tuple

from app.infrastructure.persistence.installation_repository import (
    InstallationRecord,
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
    step: int
    key: str
    state: str
    progress: int
    error: str | None


def get_setup_progress(db_path: str) -> SetupProgress:
    return _progress_from_record(InstallationRepository(db_path).get_progress())


def complete_setup_step(
    db_path: str,
    *,
    step: int,
    decision: str | None = None,
    model_reference: str | None = None,
    ollama_endpoint: str | None = None,
) -> SetupProgress:
    """Complete one ordered milestone without persisting provider secrets."""
    _validate_step_decision(step, decision, model_reference, ollama_endpoint)
    return _progress_from_record(InstallationRepository(db_path).complete_step(step))


def record_setup_task_failure(
    db_path: str,
    *,
    step: int,
    task_key: str,
    error_message: str,
) -> None:
    _require_supported_task(step, task_key)
    InstallationRepository(db_path).record_task_failure(
        step, task_key, _safe_error_message(error_message)
    )


def begin_setup_task(db_path: str, *, step: int, task_key: str) -> SetupTask:
    _require_supported_task(step, task_key)
    task = _task_from_record(InstallationRepository(db_path).begin_task(step, task_key))
    if task is None:
        raise RuntimeError("Setup 任务状态写入失败")
    return task


def update_setup_task_progress(
    db_path: str, *, step: int, task_key: str, progress: int
) -> None:
    _require_supported_task(step, task_key)
    if progress < 1 or progress > 99:
        raise ValueError("Setup 任务进度必须在 1 到 99 之间")
    InstallationRepository(db_path).update_task_progress(step, task_key, progress)


def cancel_setup_task(db_path: str, *, step: int, task_key: str) -> None:
    _require_supported_task(step, task_key)
    InstallationRepository(db_path).cancel_task(step, task_key)


def get_setup_task(db_path: str) -> SetupTask | None:
    return _task_from_record(InstallationRepository(db_path).get_progress())


def recover_interrupted_setup_task(db_path: str) -> None:
    InstallationRepository(db_path).recover_interrupted_task(_INTERRUPTED_TASK_ERROR)


def _progress_from_record(record: InstallationRecord) -> SetupProgress:
    completed = _completed_count(record)
    complete = completed == 5
    failed_step = record.active_task_step or 0
    current_step = 5 if complete else completed + 1
    if record.task_state == "failed" and failed_step in range(1, 6):
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
                    else "completed"
                    if number <= completed
                    else "pending"
                ),
                retry_action=(
                    f"retry_{record.active_task_key}"
                    if number == failed_step
                    and record.task_state == "failed"
                    and record.active_task_key
                    else None
                ),
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


def _completed_count(record: InstallationRecord) -> int:
    if record.setup_state == "completed":
        return 5
    return ("not_started", "owner", "providers", "nest", "food").index(
        record.setup_step
    )


def _validate_step_decision(
    step: int,
    decision: str | None,
    model_reference: str | None,
    ollama_endpoint: str | None,
) -> None:
    if step == 2:
        if decision not in {"bound_existing", "install_official", "skipped"}:
            raise ValueError("Ollama 步骤需要明确选择")
        if decision != "skipped" and not ollama_endpoint:
            raise ValueError("Ollama 绑定必须保存固定 endpoint")
    if step == 4 and decision not in {"configured", "skipped"}:
        raise ValueError("模型步骤需要明确选择或跳过")
    if step == 4 and decision == "configured" and not model_reference:
        raise ValueError("模型配置必须保存固定引用")


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
