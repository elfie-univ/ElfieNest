"""Focused tests for the lifecycle recovery file-lock adapter."""

from pathlib import Path

from app.orchestration.lifecycle.types import RecoveryInProgressError
from infrastructure.platform.lifecycle.recovery_lock import LocalRecoveryLockAdapter


def test_recovery_lock_excludes_service_start(tmp_path: Path) -> None:
    adapter = LocalRecoveryLockAdapter()

    with adapter.owner_recovery(tmp_path):
        assert adapter.recovery_is_active(tmp_path)
        try:
            adapter.acquire_start_lease(tmp_path)
        except RecoveryInProgressError:
            pass
        else:
            raise AssertionError("startup lease unexpectedly acquired")

    lease = adapter.acquire_start_lease(tmp_path)
    lease.release()
    assert not adapter.recovery_is_active(tmp_path)
