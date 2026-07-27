"""首次安装和 Owner 初始化功能。"""

from app.features.setup.service import (
    SetupAlreadyCompleteError,
    SetupProgress,
    SetupResult,
    SetupStep,
    complete_setup_step,
    create_first_owner,
    create_first_owner_account,
    get_setup_progress,
    needs_setup,
    record_setup_task_failure,
)

__all__ = [
    "SetupAlreadyCompleteError",
    "SetupProgress",
    "SetupResult",
    "SetupStep",
    "complete_setup_step",
    "create_first_owner",
    "create_first_owner_account",
    "get_setup_progress",
    "needs_setup",
    "record_setup_task_failure",
]
