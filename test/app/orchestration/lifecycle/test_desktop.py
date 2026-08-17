from pathlib import Path
from typing import cast

from app.orchestration.lifecycle import desktop
from app.orchestration.lifecycle.ports import DesktopHostPort
from app.orchestration.lifecycle.types import ServiceLifecycleResult


class AbsentDesktopHost:
    def process_id(self, elfie_home: Path):
        return None


class BackgroundDesktopHost:
    def __init__(self, executable: Path) -> None:
        self.executable = executable
        self.commands: list[tuple[str, ...]] = []
        self.events: list[str] = []
        self.process = type("Process", (), {"pid": 77, "poll": lambda _self: None})()

    def process_id(self, _elfie_home: Path):
        return None

    def find_executable(self, _project_root: Path):
        return self.executable

    def launch(self, command, _cwd):
        self.events.append("launch")
        self.commands.append(tuple(command))
        return self.process

    def write_receipt(self, _elfie_home: Path, _pid: int) -> None:
        self.events.append("receipt")

    def exists(self, _pid: int) -> bool:
        return True


class RecoveringDesktopHost(BackgroundDesktopHost):
    def __init__(self, executable: Path) -> None:
        super().__init__(executable)
        self.ready = False

    def process_id(self, _elfie_home: Path):
        return 55


class ActivationHelperDesktopHost(BackgroundDesktopHost):
    def __init__(self, executable: Path) -> None:
        super().__init__(executable)
        self.process = type("Process", (), {"pid": 77, "poll": lambda _self: 0})()


def test_existing_controller_is_woken_when_server_is_not_ready(tmp_path: Path) -> None:
    executable = tmp_path / "ElfieNest"
    executable.write_text("binary", encoding="utf-8")
    host = RecoveringDesktopHost(executable)
    clock = iter([0.0, 0.0, 0.1, 0.1])

    result = desktop.start_desktop_application(
        tmp_path / "home",
        tmp_path,
        host=cast(DesktopHostPort, host),
        health_checker=lambda: host.ready,
        timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        monotonic=lambda: next(clock, 0.2),
        sleeper=lambda _delay: setattr(host, "ready", True),
    )

    assert result.status == "already_running"
    assert result.pid == 55
    assert host.commands == [(str(executable), "--background")]


def test_background_desktop_starts_controller_without_viewer(tmp_path: Path) -> None:
    executable = tmp_path / "ElfieNest"
    executable.write_text("binary", encoding="utf-8")
    host = BackgroundDesktopHost(executable)

    result = desktop.start_desktop_application(
        tmp_path / "home",
        tmp_path,
        host=cast(DesktopHostPort, host),
        health_checker=lambda: True,
        background=True,
    )

    assert result.status == "started"
    assert host.commands == [(str(executable), "--background")]
    assert host.events == ["launch", "receipt"]


def test_desktop_pid_receipt_is_written_only_after_runtime_health(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ElfieNest"
    executable.write_text("binary", encoding="utf-8")
    host = BackgroundDesktopHost(executable)

    def health_check() -> bool:
        assert host.events == ["launch"]
        return True

    result = desktop.start_desktop_application(
        tmp_path / "home",
        tmp_path,
        host=cast(DesktopHostPort, host),
        health_checker=health_check,
        background=True,
    )

    assert result.status == "started"
    assert host.events == ["launch", "receipt"]


def test_activation_helper_reuses_ready_controller_without_a_pid_receipt(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ElfieNest"
    executable.write_text("binary", encoding="utf-8")
    host = ActivationHelperDesktopHost(executable)
    checks = iter([False, True])
    clock = iter([0.0, 0.0, 0.1])

    result = desktop.start_desktop_application(
        tmp_path / "home",
        tmp_path,
        host=cast(DesktopHostPort, host),
        health_checker=lambda: next(checks),
        timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        monotonic=lambda: next(clock),
        sleeper=lambda _delay: None,
    )

    assert result.status == "already_running"
    assert result.pid is None
    assert host.events == ["launch"]


def test_stop_desktop_is_idempotent_without_pid_receipt(tmp_path: Path) -> None:
    result = desktop.stop_desktop_application(
        tmp_path, host=cast(DesktopHostPort, AbsentDesktopHost())
    )

    assert result == ServiceLifecycleResult(status="already_stopped")
