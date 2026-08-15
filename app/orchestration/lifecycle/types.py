"""Frozen results and typed errors for service lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple


class ServiceLifecycleError(Exception):
    """Base class for expected service lifecycle errors."""


class FrontendPreparationError(ServiceLifecycleError):
    """The source Web client could not be prepared for Runtime launch."""


@dataclass(frozen=True)
class DataHomeRecoveryError(ServiceLifecycleError):
    """The selected data root could not be preserved and rebuilt safely."""

    detail: str

    def __str__(self) -> str:
        return f"Data-root recovery failed: {self.detail}"


@dataclass(frozen=True)
class RecoveryInProgressError(ServiceLifecycleError):
    """A startup or recovery operation could not acquire the lifecycle lease."""

    path: Path

    def __str__(self) -> str:
        return f"Owner recovery is already in progress: {self.path}"


@dataclass(frozen=True)
class SnapshotRecoveryRequiredError(ServiceLifecycleError):
    """The selected data root cannot be treated as a fresh Runtime root."""

    path: Path
    detail: str

    def __str__(self) -> str:
        return f"Runtime snapshot recovery is required ({self.path}): {self.detail}"


@dataclass(frozen=True)
class LifecycleBusyError(ServiceLifecycleError):
    """A different lifecycle operation currently owns the generation."""

    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True)
class AuthorityHostError(ServiceLifecycleError):
    """The configured Godot authority host could not be started or stopped safely."""

    detail: str

    def __str__(self) -> str:
        return f"Godot authority host failed: {self.detail}"


@dataclass(frozen=True)
class InvalidPidFileError(ServiceLifecycleError):
    path: Path
    content: str

    def __str__(self) -> str:
        return f"Invalid PID file content ({self.path}): {self.content!r}"


@dataclass(frozen=True)
class ProcessIdentityMismatchError(ServiceLifecycleError):
    pid: int
    expected_cwd: Path
    actual_cwd: Path
    expected_script: Path
    actual_command: Tuple[str, ...]

    def __str__(self) -> str:
        return f"PID {self.pid} is not a current project ElfieNest service process"


@dataclass(frozen=True)
class ProcessInspectionError(ServiceLifecycleError):
    pid: int
    detail: str

    def __str__(self) -> str:
        return f"Cannot check PID {self.pid}: {self.detail}"


@dataclass(frozen=True)
class StopTimeoutError(ServiceLifecycleError):
    pid: int
    timeout_seconds: float

    def __str__(self) -> str:
        return f"PID {self.pid} did not stop within {self.timeout_seconds:g} seconds"


@dataclass(frozen=True)
class SignalProcessError(ServiceLifecycleError):
    pid: int
    detail: str

    def __str__(self) -> str:
        return f"Cannot send SIGTERM to PID {self.pid}: {self.detail}"


@dataclass(frozen=True)
class LaunchFailedError(ServiceLifecycleError):
    detail: str

    def __str__(self) -> str:
        return f"Service process launch failed: {self.detail}"


@dataclass(frozen=True)
class HealthCheckFailedError(ServiceLifecycleError):
    pid: int
    timeout_seconds: float

    def __str__(self) -> str:
        return f"PID {self.pid} did not pass health check within {self.timeout_seconds:g} seconds"


@dataclass(frozen=True)
class CleanupFailedError(ServiceLifecycleError):
    pid: int
    detail: str

    def __str__(self) -> str:
        return f"PID {self.pid} failed health check and cannot be terminated: {self.detail}"


@dataclass(frozen=True)
class ServicePortsActiveError(ServiceLifecycleError):
    detail: str

    def __str__(self) -> str:
        return (
            f"Service port still in use, cannot confirm service stopped: {self.detail}"
        )


@dataclass(frozen=True)
class ServiceLifecycleResult:
    """Immutable result of a lifecycle operation."""

    status: Literal[
        "started", "already_running", "stopped", "already_stopped", "failed"
    ]
    pid: Optional[int] = None
    error: Optional[ServiceLifecycleError] = None
    command: Optional[Tuple[str, ...]] = None
