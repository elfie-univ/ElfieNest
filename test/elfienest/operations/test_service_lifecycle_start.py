from __future__ import annotations

import signal
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import List, Tuple

import pytest
from _pytest.monkeypatch import MonkeyPatch

from elfienest.operations import service_lifecycle
from elfienest.operations.recovery_lock import acquire_service_start_lease
from elfienest.operations.service_lifecycle import (
    HealthCheckFailedError,
    LaunchFailedError,
    ServiceLifecycleResult,
    start_service,
)
from elfienest.operations.service_lifecycle_types import CleanupFailedError
from test.elfienest.operations.service_lifecycle_fakes import (
    FailingInspector,
    FakeClock,
    FakeInspector,
    RecordingLauncher,
)


def test_start_writes_pid_before_health_check_and_returns_started(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5101)
    inspector = FakeInspector(
        cwd=project_root,
        command=("python", "scripts/serve.py"),
        existence=[True],
    )
    health_observations: List[str] = []

    def healthy() -> bool:
        health_observations.append(
            (elfie_home / "elfienest.pid").read_text(encoding="utf-8")
        )
        return True

    # When
    result = start_service(
        elfie_home,
        project_root,
        launcher=launcher,
        inspector=inspector,
        health_checker=healthy,
    )

    # Then
    assert result.status == "started"
    assert result.pid == 5101
    assert launcher.calls[0][0][1] == str(
        (project_root / "scripts" / "serve.py").resolve()
    )
    assert launcher.calls[0][0][2:] == ("--fallback",)
    assert launcher.calls[0][1] == project_root.resolve()
    assert health_observations == ["5101"]


def test_start_refuses_to_launch_while_another_start_holds_lease(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5109)
    lease = acquire_service_start_lease(elfie_home)

    try:
        result = start_service(
            elfie_home,
            project_root,
            launcher=launcher,
            inspector=FailingInspector(),
            health_checker=lambda: True,
        )
    finally:
        lease.release()

    assert result.status == "failed"
    assert launcher.calls == []


def test_start_preserves_supplied_service_command(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5104)
    command = (
        "/custom/python",
        "scripts/serve.py",
        "--fallback",
        "--port",
        "8100",
        "--ws-port=8866",
    )
    inspector = FakeInspector(
        cwd=project_root,
        command=command,
        existence=[True],
    )

    # When
    result = start_service(
        elfie_home,
        project_root,
        command=command,
        launcher=launcher,
        inspector=inspector,
        health_checker=lambda: True,
    )

    # Then
    assert result.status == "started"
    assert launcher.calls[0][0] == command
    assert result.command == command


def test_start_health_failure_terminates_process_and_removes_pid(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5102)
    signals: List[Tuple[int, int]] = []
    clock = FakeClock()
    inspector = FakeInspector(
        cwd=project_root,
        command=("python", "scripts/serve.py"),
        existence=[True, True, True, True, False],
    )

    # When
    result = start_service(
        elfie_home,
        project_root,
        launcher=launcher,
        health_checker=lambda: False,
        signaler=lambda pid, sig: signals.append((pid, sig)),
        inspector=inspector,
        timeout_seconds=0.2,
        poll_interval_seconds=0.1,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, HealthCheckFailedError)
    assert signals == [(5102, signal.SIGTERM)]
    assert not (elfie_home / "elfienest.pid").exists()


def test_start_cleanup_preserves_pid_receipt_replaced_by_another_process(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5107)
    inspector = FakeInspector(
        cwd=project_root,
        command=("python", "scripts/serve.py"),
        existence=[True, True, False],
    )

    def replace_receipt(_pid: int, _sig: int) -> None:
        (elfie_home / "elfienest.pid").write_text("9999", encoding="utf-8")

    result = start_service(
        elfie_home,
        project_root,
        launcher=launcher,
        health_checker=lambda: False,
        signaler=replace_receipt,
        inspector=inspector,
        timeout_seconds=0.0,
    )

    assert result.status == "failed"
    assert (elfie_home / "elfienest.pid").read_text(encoding="utf-8") == "9999"


def test_start_cleanup_does_not_signal_reused_pid(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5108)
    inspector = FakeInspector(
        cwd=tmp_path / "other-project",
        command=("python", "unrelated.py"),
        existence=[True, True],
    )
    signals: List[Tuple[int, int]] = []

    result = start_service(
        elfie_home,
        project_root,
        launcher=launcher,
        health_checker=lambda: False,
        signaler=lambda pid, sig: signals.append((pid, sig)),
        inspector=inspector,
        timeout_seconds=0.0,
    )

    assert result.status == "failed"
    assert isinstance(result.error, CleanupFailedError)
    assert signals == []
    assert (elfie_home / "elfienest.pid").exists()


def test_start_health_cleanup_timeout_keeps_pid_receipt(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5105)
    inspector = FakeInspector(
        cwd=project_root,
        command=("python", "scripts/serve.py"),
        existence=[True],
    )
    clock = FakeClock()

    # When
    result = start_service(
        elfie_home,
        project_root,
        launcher=launcher,
        inspector=inspector,
        health_checker=lambda: False,
        signaler=lambda _pid, _sig: None,
        timeout_seconds=0.2,
        poll_interval_seconds=0.1,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, CleanupFailedError)
    assert (elfie_home / "elfienest.pid").exists()


def test_start_pid_registration_failure_cleans_up_launched_process(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5106)
    inspector = FakeInspector(
        cwd=project_root,
        command=("python", "scripts/serve.py"),
        existence=[True, False],
    )
    signals: List[Tuple[int, int]] = []

    def fail_registration(_home: Path, _pid: int) -> Path:
        raise PermissionError("read-only home")

    monkeypatch.setattr(
        service_lifecycle, "register_service_process", fail_registration
    )

    # When
    result = start_service(
        elfie_home,
        project_root,
        launcher=launcher,
        inspector=inspector,
        health_checker=lambda: True,
        signaler=lambda pid, sig: signals.append((pid, sig)),
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, LaunchFailedError)
    assert signals == [(5106, signal.SIGTERM)]


def test_lifecycle_result_is_frozen() -> None:
    # Given
    result = ServiceLifecycleResult(status="already_stopped")

    # When / Then
    with pytest.raises(FrozenInstanceError):
        result.pid = 1
