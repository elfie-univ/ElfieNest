"""首次安装和 Owner 初始化功能。"""

from app.features.setup.service import (
    SetupAlreadyCompleteError,
    has_owner,
    needs_setup,
)

__all__ = [
    "SetupAlreadyCompleteError",
    "has_owner",
    "needs_setup",
]
