"""Owner 恢复与普通服务启动之间的本机进程锁。"""

from __future__ import annotations

import atexit
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterator, Optional

from elfienest.operations.service_process import secure_elfie_home

if os.name == "nt":
    import msvcrt
else:
    import fcntl

LOCK_FILENAME: Final = "owner-recovery.lock"
MANAGED_START_ENV: Final = "ELFIENEST_MANAGED_START"


@dataclass(frozen=True)
class RecoveryInProgressError(Exception):
    path: Path

    def __str__(self) -> str:
        return f"已有 Owner 恢复操作正在执行: {self.path}"


class ServiceStartLease:
    """普通服务启动期间持有的独占锁，PID 登记后主动释放。"""

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
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(elfie_home / LOCK_FILENAME, flags, 0o600)
    if os.name != "nt":
        os.fchmod(descriptor, 0o600)
    if os.fstat(descriptor).st_size == 0:
        os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
    return descriptor


def _lock(descriptor: int, *, blocking: bool) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(descriptor, mode, 1)
        except OSError as error:
            raise BlockingIOError from error
        return
    operation = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
    fcntl.flock(descriptor, operation)


def _unlock(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def owner_recovery_lock(elfie_home: Path) -> Iterator[None]:
    """持有 Owner 恢复独占锁，阻止并发恢复和普通服务启动。"""
    descriptor = _open_lock(elfie_home)
    try:
        try:
            _lock(descriptor, blocking=False)
        except BlockingIOError as error:
            raise RecoveryInProgressError(elfie_home / LOCK_FILENAME) from error
        yield
    finally:
        _unlock(descriptor)
        os.close(descriptor)


def service_start_is_blocked(elfie_home: Path) -> bool:
    """检测普通服务启动是否与 Owner 恢复临界区冲突。"""
    try:
        lease = acquire_service_start_lease(elfie_home)
    except (OSError, RecoveryInProgressError):
        return True
    lease.release()
    return False


def acquire_service_start_lease(
    elfie_home: Path, *, blocking: bool = False
) -> ServiceStartLease:
    """串行化服务启动，并持锁到 PID 已登记可被精确停止。"""
    descriptor = _open_lock(elfie_home)
    try:
        _lock(descriptor, blocking=blocking)
    except BlockingIOError as error:
        os.close(descriptor)
        raise RecoveryInProgressError(elfie_home / LOCK_FILENAME) from error
    lease = ServiceStartLease(descriptor)
    atexit.register(lease.release)
    return lease
