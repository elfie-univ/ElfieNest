from __future__ import annotations

from pathlib import Path

import pytest

from app.orchestration.lifecycle.recovery_lock import (
    RecoveryInProgressError,
    acquire_service_start_lease,
    owner_recovery_lock,
    service_start_is_blocked,
)


def test_owner_recovery_lock_blocks_normal_service_start(tmp_path: Path) -> None:
    elfie_home = tmp_path / "home"

    with owner_recovery_lock(elfie_home):
        assert service_start_is_blocked(elfie_home) is True

    assert service_start_is_blocked(elfie_home) is False


def test_owner_recovery_lock_rejects_concurrent_recovery(tmp_path: Path) -> None:
    elfie_home = tmp_path / "home"

    with owner_recovery_lock(elfie_home):
        with pytest.raises(RecoveryInProgressError):
            with owner_recovery_lock(elfie_home):
                raise AssertionError("并发恢复不应进入临界区")


def test_service_start_lease_blocks_recovery_until_pid_handoff(
    tmp_path: Path,
) -> None:
    elfie_home = tmp_path / "home"
    lease = acquire_service_start_lease(elfie_home)

    with pytest.raises(RecoveryInProgressError):
        with owner_recovery_lock(elfie_home):
            raise AssertionError("PID 登记前恢复不应进入临界区")

    lease.release()
    with owner_recovery_lock(elfie_home):
        assert service_start_is_blocked(elfie_home) is True


def test_service_start_lease_rejects_concurrent_service_start(tmp_path: Path) -> None:
    elfie_home = tmp_path / "home"
    lease = acquire_service_start_lease(elfie_home)

    with pytest.raises(RecoveryInProgressError):
        acquire_service_start_lease(elfie_home)

    lease.release()
