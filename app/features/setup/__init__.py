"""首次安装和 Owner 初始化功能。"""

from app.features.setup.service import (
    SetupAlreadyCompleteError,
    SetupResult,
    create_first_owner,
    create_first_owner_account,
    needs_setup,
)

__all__ = [
    "SetupAlreadyCompleteError",
    "SetupResult",
    "create_first_owner",
    "create_first_owner_account",
    "needs_setup",
]
