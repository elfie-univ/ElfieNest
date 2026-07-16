"""服务生命周期操作的冻结结果与类型化错误。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple


class ServiceLifecycleError(Exception):
    """服务生命周期可预期错误的基类。"""


@dataclass(frozen=True)
class InvalidPidFileError(ServiceLifecycleError):
    path: Path
    content: str

    def __str__(self) -> str:
        return f"PID 文件内容无效 ({self.path}): {self.content!r}"


@dataclass(frozen=True)
class ProcessIdentityMismatchError(ServiceLifecycleError):
    pid: int
    expected_cwd: Path
    actual_cwd: Path
    expected_script: Path
    actual_command: Tuple[str, ...]

    def __str__(self) -> str:
        return f"PID {self.pid} 不是当前项目的 ElfieNest 服务进程"


@dataclass(frozen=True)
class ProcessInspectionError(ServiceLifecycleError):
    pid: int
    detail: str

    def __str__(self) -> str:
        return f"无法检查 PID {self.pid}: {self.detail}"


@dataclass(frozen=True)
class StopTimeoutError(ServiceLifecycleError):
    pid: int
    timeout_seconds: float

    def __str__(self) -> str:
        return f"PID {self.pid} 在 {self.timeout_seconds:g} 秒内未停止"


@dataclass(frozen=True)
class SignalProcessError(ServiceLifecycleError):
    pid: int
    detail: str

    def __str__(self) -> str:
        return f"无法向 PID {self.pid} 发送 SIGTERM: {self.detail}"


@dataclass(frozen=True)
class LaunchFailedError(ServiceLifecycleError):
    detail: str

    def __str__(self) -> str:
        return f"服务进程启动失败: {self.detail}"


@dataclass(frozen=True)
class HealthCheckFailedError(ServiceLifecycleError):
    pid: int
    timeout_seconds: float

    def __str__(self) -> str:
        return f"PID {self.pid} 在 {self.timeout_seconds:g} 秒内未通过健康检查"


@dataclass(frozen=True)
class CleanupFailedError(ServiceLifecycleError):
    pid: int
    detail: str

    def __str__(self) -> str:
        return f"PID {self.pid} 健康检查失败且无法终止: {self.detail}"


@dataclass(frozen=True)
class ServicePortsActiveError(ServiceLifecycleError):
    detail: str

    def __str__(self) -> str:
        return f"服务端口仍在使用，无法确认服务已停止: {self.detail}"


@dataclass(frozen=True)
class ServiceLifecycleResult:
    """一次生命周期操作的不可变结果。"""

    status: Literal[
        "started", "already_running", "stopped", "already_stopped", "failed"
    ]
    pid: Optional[int] = None
    error: Optional[ServiceLifecycleError] = None
    command: Optional[Tuple[str, ...]] = None
