"""Local file-lock adapter for lifecycle startup and Owner recovery exclusion."""

from __future__ import annotations

import atexit
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Final, Iterator, Optional, cast

from app.orchestration.lifecycle.ports import LifecycleLease
from app.orchestration.lifecycle.types import RecoveryInProgressError
from infrastructure.platform.lifecycle.process import secure_elfie_home

if os.name == "nt":
    import msvcrt
else:
    import fcntl

LOCK_FILENAME: Final = "owner-recovery.lock"
MANAGED_START_ENV: Final = "ELFIENEST_MANAGED_START"


class _FileLifecycleLease:
    """Exclusive lock held during normal service startup and released after PID registration."""

    def __init__(self, descriptor: int) -> None:
        self._descriptor: Optional[int] = descriptor

    def release(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            return
        self._descriptor = None
        _unlock(descriptor)
        os.close(descriptor)


def _open_lock(elfie_home: Path) -> int:
    secure_elfie_home(elfie_home)
    lock_dir = elfie_home / "runtime" / "locks"
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_dir / LOCK_FILENAME, flags, 0o600)
    if os.name != "nt":
        os.fchmod(descriptor, 0o600)
    if os.fstat(descriptor).st_size == 0:
        os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
    return descriptor


def _lock(descriptor: int, *, blocking: bool) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt_module = cast(Any, msvcrt)
        mode = int(msvcrt_module.LK_LOCK if blocking else msvcrt_module.LK_NBLCK)
        locking = cast(Callable[[int, int, int], None], msvcrt_module.locking)
        try:
            locking(descriptor, mode, 1)
        except OSError as error:
            raise BlockingIOError from error
        return
    operation = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
    fcntl.flock(descriptor, operation)


def _unlock(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt_module = cast(Any, msvcrt)
        locking = cast(Callable[[int, int, int], None], msvcrt_module.locking)
        locking(descriptor, int(msvcrt_module.LK_UNLCK), 1)
        return
    fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def owner_recovery_lock(elfie_home: Path) -> Iterator[None]:
    """Hold the owner recovery lock to block concurrent recovery and normal startup."""
    descriptor = _open_lock(elfie_home)
    try:
        try:
            _lock(descriptor, blocking=False)
        except BlockingIOError as error:
            raise RecoveryInProgressError(
                elfie_home / "runtime" / "locks" / LOCK_FILENAME
            ) from error
        yield
    finally:
        _unlock(descriptor)
        os.close(descriptor)


def service_start_is_blocked(elfie_home: Path) -> bool:
    """Detect whether normal service startup conflicts with Owner recovery."""
    try:
        lease = acquire_service_start_lease(elfie_home)
    except (OSError, RecoveryInProgressError):
        return True
    lease.release()
    return False


def acquire_service_start_lease(
    elfie_home: Path, *, blocking: bool = False
) -> LifecycleLease:
    """Serialize service startup and hold the lock until the PID can be stopped precisely."""
    descriptor = _open_lock(elfie_home)
    try:
        _lock(descriptor, blocking=blocking)
    except BlockingIOError as error:
        os.close(descriptor)
        raise RecoveryInProgressError(
            elfie_home / "runtime" / "locks" / LOCK_FILENAME
        ) from error
    lease = _FileLifecycleLease(descriptor)
    atexit.register(lease.release)
    return lease


class LocalRecoveryLockAdapter:
    """Operating-system file-lock implementation of the recovery-lock Port."""

    def acquire_start_lease(
        self, elfie_home: Path, *, blocking: bool = False
    ) -> LifecycleLease:
        return acquire_service_start_lease(elfie_home, blocking=blocking)

    def recovery_is_active(self, elfie_home: Path) -> bool:
        return service_start_is_blocked(elfie_home)

    @contextmanager
    def owner_recovery(self, elfie_home: Path) -> Iterator[None]:
        with owner_recovery_lock(elfie_home):
            yield
