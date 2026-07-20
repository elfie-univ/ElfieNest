"""代码执行工具的安全边界。

生产环境在接入真正的 OS/container sandbox 之前，禁止执行任意 Python 子进程。
"""

from __future__ import annotations

from typing import Any, Dict


class CodeSandboxUnavailableError(RuntimeError):
    """当前运行环境没有可验证的真实代码隔离能力。"""


class CodeSandboxPlugin:
    """占位的代码工具；未接入真实隔离实现前始终拒绝执行。"""

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        """返回生产代码执行能力是否已接入真实隔离后端。"""
        return False

    def execute(self, code: str) -> Dict[str, Any]:
        """拒绝执行未隔离代码，避免把宿主进程伪装成沙箱。"""
        _ = code
        raise CodeSandboxUnavailableError(
            "代码执行已禁用：当前未接入真实隔离 sandbox，不能执行宿主 Python 子进程"
        )
