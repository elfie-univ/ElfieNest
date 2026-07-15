from __future__ import annotations

import signal
from pathlib import Path
from typing import List, Tuple

from _pytest.monkeypatch import MonkeyPatch

from elfienest.operations import service_lifecycle
from elfienest.operations.service_lifecycle import (
    InvalidPidFileError,
    ProcessIdentityMismatchError,
    ServicePortsActiveError,
    StopTimeoutError,
    stop_service,
)
from test.elfienest.operations.service_lifecycle_fakes import (
    FailingInspector,
    FakeClock,
    FakeInspector,
    serve_command,
    write_pid,
)


def test_stop_is_already_stopped_without_pid_file(tmp_path: Path) -> None:
    # Given
    elfie_home = tmp_path / "home"

    # When
    result = stop_service(
        elfie_home,
        tmp_path / "project",
        inspector=FailingInspector(),
        service_ports_in_use=lambda _ports: False,
    )

    # Then
    assert result.status == "already_stopped"
    assert result.pid is None


def test_stop_fails_closed_without_pid_when_service_ports_are_active(
    tmp_path: Path,
) -> None:
    # Given
    elfie_home = tmp_path / "home"

    # When
    result = stop_service(
        elfie_home,
        tmp_path / "project",
        inspector=FailingInspector(),
        service_ports_in_use=lambda _ports: True,
    )

    # Then
    assert result.status == "failed"
    assert result.error is not None
    assert "PID" in str(result.error)


def test_stop_rejects_non_target_process_without_signal(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    pid_path = write_pid(elfie_home, 4101)
    inspector = FakeInspector(
        cwd=tmp_path / "other-project",
        command=serve_command(project_root),
        existence=[True],
    )
    signals: List[Tuple[int, int]] = []

    # When
    result = stop_service(
        elfie_home,
        project_root,
        inspector=inspector,
        signaler=lambda pid, sig: signals.append((pid, sig)),
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, ProcessIdentityMismatchError)
    assert signals == []
    assert pid_path.exists()


def test_stop_signals_verified_target_and_removes_pid_file(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    pid_path = write_pid(elfie_home, 4102)
    inspector = FakeInspector(
        cwd=project_root.resolve(),
        command=serve_command(project_root),
        existence=[True, True, False],
    )
    signals: List[Tuple[int, int]] = []
    clock = FakeClock()

    # When
    result = stop_service(
        elfie_home,
        project_root,
        inspector=inspector,
        signaler=lambda pid, sig: signals.append((pid, sig)),
        timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
        service_ports_in_use=lambda _ports: False,
    )

    # Then
    assert result.status == "stopped"
    assert result.pid == 4102
    assert result.command == serve_command(project_root)
    assert signals == [(4102, signal.SIGTERM)]
    assert not pid_path.exists()


def test_stop_accepts_relative_serve_script_from_verified_working_directory(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    write_pid(elfie_home, 4104)
    inspector = FakeInspector(
        cwd=project_root.resolve(),
        command=("python", "scripts/serve.py", "--fallback"),
        existence=[True, True, False],
    )
    signals: List[Tuple[int, int]] = []

    # When
    result = stop_service(
        elfie_home,
        project_root,
        inspector=inspector,
        signaler=lambda pid, sig: signals.append((pid, sig)),
        service_ports_in_use=lambda _ports: False,
    )

    # Then
    assert result.status == "stopped"
    assert signals == [(4104, signal.SIGTERM)]


def test_stop_fails_when_target_ports_remain_active(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    pid_path = write_pid(elfie_home, 4105)
    inspector = FakeInspector(
        cwd=project_root.resolve(),
        command=serve_command(project_root),
        existence=[True, True, False],
    )

    # When
    result = stop_service(
        elfie_home,
        project_root,
        inspector=inspector,
        signaler=lambda pid, sig: None,
        service_ports_in_use=lambda _ports: True,
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, ServicePortsActiveError)
    assert pid_path.exists()


def test_stop_timeout_keeps_pid_receipt_for_retry(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    pid_path = write_pid(elfie_home, 4103)
    inspector = FakeInspector(
        cwd=project_root.resolve(),
        command=serve_command(project_root),
        existence=[True],
    )
    clock = FakeClock()

    # When
    result = stop_service(
        elfie_home,
        project_root,
        inspector=inspector,
        signaler=lambda pid, sig: None,
        timeout_seconds=0.2,
        poll_interval_seconds=0.1,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, StopTimeoutError)
    assert pid_path.exists()


def test_stop_rejects_invalid_pid_file_with_typed_error(tmp_path: Path) -> None:
    # Given
    elfie_home = tmp_path / "home"
    elfie_home.mkdir()
    (elfie_home / "elfienest.pid").write_text("not-a-pid", encoding="utf-8")

    # When
    result = stop_service(
        elfie_home,
        tmp_path / "project",
        inspector=FailingInspector(),
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, InvalidPidFileError)


def test_stop_reports_unreadable_pid_receipt_as_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    elfie_home = tmp_path / "home"
    write_pid(elfie_home, 4106)

    def fail_read(_path: Path):
        raise PermissionError("receipt denied")

    monkeypatch.setattr(service_lifecycle, "_read_pid", fail_read)

    result = stop_service(
        elfie_home,
        tmp_path / "project",
        inspector=FailingInspector(),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "PID" in str(result.error)
