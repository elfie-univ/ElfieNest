from pathlib import Path

from app.orchestration.lifecycle.service import stop_service
from app.orchestration.lifecycle.types import (
    InvalidPidFileError,
    ProcessIdentityMismatchError,
    ServicePortsActiveError,
    StopTimeoutError,
)
from test.app.orchestration.lifecycle.service_fakes import (
    FakeClock,
    FakeProcessPort,
    serve_command,
    write_pid,
)


def test_stop_without_receipt_is_already_stopped(tmp_path: Path) -> None:
    port = FakeProcessPort(cwd=tmp_path)
    result = stop_service(tmp_path / "home", tmp_path, process_port=port)
    assert result.status == "already_stopped"


def test_stop_fails_closed_without_receipt_when_ports_active(tmp_path: Path) -> None:
    port = FakeProcessPort(cwd=tmp_path, ports_active=True)
    result = stop_service(tmp_path / "home", tmp_path, process_port=port)
    assert isinstance(result.error, ServicePortsActiveError)


def test_stop_rejects_mismatched_process_without_signal(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_pid(home, 4101)
    port = FakeProcessPort(
        cwd=tmp_path / "other", command=serve_command(tmp_path), existence=(True,)
    )
    result = stop_service(home, tmp_path, process_port=port)
    assert isinstance(result.error, ProcessIdentityMismatchError)
    assert port.terminations == []


def test_stop_verified_process_and_remove_receipt(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_pid(home, 4102)
    port = FakeProcessPort(
        cwd=tmp_path.resolve(),
        command=serve_command(tmp_path),
        existence=(True, True, False),
    )
    result = stop_service(home, tmp_path, process_port=port)
    assert result.status == "stopped"
    assert port.terminations == [(4102, False)]
    assert not (home / "elfienest.pid").exists()


def test_stop_accepts_the_injected_frozen_core_command(tmp_path: Path) -> None:
    home = tmp_path / "home"
    core = (
        tmp_path
        / "ElfieNest.app"
        / "Contents"
        / "Resources"
        / "python-core"
        / "ElfieNestCore"
    )
    command = (str(core), "--port", "8002")
    write_pid(home, 4105)
    port = FakeProcessPort(
        cwd=tmp_path.resolve(),
        command=command,
        existence=(True, True, False),
    )

    result = stop_service(
        home,
        tmp_path,
        process_port=port,
        expected_command=(str(core),),
    )

    assert result.status == "stopped"
    assert port.terminations == [(4105, False)]


def test_stop_accepts_frozen_core_path_with_spaces_from_macos_ps(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    core = tmp_path / "ElfieNest app" / "Contents" / "Resources" / "ElfieNestCore"
    write_pid(home, 4106)
    port = FakeProcessPort(
        cwd=tmp_path.resolve(),
        command=tuple(str(core).split(" ")) + ("--force",),
        existence=(True, True, False),
    )

    # `ps` returns an unquoted command string; the platform inspector's
    # `shlex.split` presents that executable as separate tokens. Keep the
    # fixture explicit rather than weakening identity checks globally.
    result = stop_service(
        home,
        tmp_path,
        process_port=port,
        expected_command=(str(core),),
    )

    assert result.status == "stopped"
    assert port.terminations == [(4106, False)]


def test_stop_timeout_keeps_receipt(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_pid(home, 4103)
    clock = FakeClock()
    port = FakeProcessPort(
        cwd=tmp_path.resolve(), command=serve_command(tmp_path), existence=(True,)
    )
    result = stop_service(
        home,
        tmp_path,
        process_port=port,
        timeout_seconds=0.2,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )
    assert isinstance(result.error, StopTimeoutError)
    assert (home / "elfienest.pid").exists()


def test_stop_escalates_to_force_after_graceful_timeout(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_pid(home, 4107)
    clock = FakeClock()

    class ForceStopsPort(FakeProcessPort):
        def terminate(self, pid: int, *, force: bool = False) -> None:
            super().terminate(pid, force=force)
            if force:
                self.existence = [False]

    port = ForceStopsPort(
        cwd=tmp_path.resolve(),
        command=serve_command(tmp_path),
        existence=(True, True, True, True),
    )

    result = stop_service(
        home,
        tmp_path,
        process_port=port,
        timeout_seconds=5.0,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert result.status == "stopped"
    assert port.terminations == [(4107, False), (4107, True)]


def test_stop_invalid_or_unreadable_receipt_returns_typed_error(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_pid(home, 4104).write_text("bad", encoding="utf-8")
    port = FakeProcessPort(cwd=tmp_path)
    assert isinstance(
        stop_service(home, tmp_path, process_port=port).error, InvalidPidFileError
    )
    port.read_error = PermissionError("denied")
    assert stop_service(home, tmp_path, process_port=port).status == "failed"


def test_stop_handles_receipt_disappearing_during_read(tmp_path: Path) -> None:
    class DisappearingReceiptPort(FakeProcessPort):
        def receipt_exists(self, elfie_home: Path) -> bool:
            return True

        def read_receipt(self, elfie_home: Path) -> None:
            return None

    port = DisappearingReceiptPort(cwd=tmp_path)

    result = stop_service(tmp_path / "home", tmp_path, process_port=port)

    assert result.status == "already_stopped"
