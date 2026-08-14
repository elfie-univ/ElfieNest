from pathlib import Path

from app.orchestration.lifecycle.service import start_service
from app.orchestration.lifecycle.types import (
    CleanupFailedError,
    HealthCheckFailedError,
    ServicePortsActiveError,
)
from test.app.orchestration.lifecycle.service_fakes import (
    FakeClock,
    FakeProcessPort,
    FakeRecoveryLock,
    write_pid,
)


def test_start_registers_pid_before_health_and_preserves_environment(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    port = FakeProcessPort(cwd=tmp_path, launched_pid=5101)
    observations: list[str] = []

    result = start_service(
        home,
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(),
        health_checker=lambda: (
            observations.append((home / "elfienest.pid").read_text(encoding="utf-8"))
            or True
        ),
        child_environment={"ELFIE_HOME": str(home)},
    )

    assert result.status == "started"
    assert observations == ["5101"]
    assert port.launches[0][2]["ELFIENEST_MANAGED_START"] == "1"
    assert port.launches[0][2]["ELFIE_HOME"] == str(home)


def test_start_is_blocked_by_recovery_lock(tmp_path: Path) -> None:
    port = FakeProcessPort(cwd=tmp_path)
    result = start_service(
        tmp_path / "home",
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(blocked=True),
        health_checker=lambda: True,
    )
    assert result.status == "failed"
    assert port.launches == []


def test_start_rejects_existing_service_on_different_ports(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_pid(home, 5103)
    port = FakeProcessPort(
        cwd=tmp_path,
        command=("python", "scripts/serve.py", "--port", "8000"),
    )
    result = start_service(
        home,
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(),
        command=("python", "scripts/serve.py", "--port", "8100"),
        health_checker=lambda: True,
    )
    assert result.status == "failed"
    assert "different ports" in str(result.error)


def test_start_checks_health_of_existing_service(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_pid(home, 5110)
    port = FakeProcessPort(cwd=tmp_path)
    result = start_service(
        home,
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(),
        health_checker=lambda: False,
    )
    assert isinstance(result.error, HealthCheckFailedError)
    assert port.launches == []


def test_start_health_timeout_cleans_process_and_receipt(tmp_path: Path) -> None:
    home = tmp_path / "home"
    clock = FakeClock()
    port = FakeProcessPort(
        cwd=tmp_path,
        existence=(True, True, True, False),
        launched_pid=5102,
    )
    result = start_service(
        home,
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(),
        health_checker=lambda: False,
        timeout_seconds=0.1,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )
    assert isinstance(result.error, HealthCheckFailedError)
    assert port.terminations == [(5102, False)]
    assert not (home / "elfienest.pid").exists()


def test_start_health_timeout_cleans_an_injected_frozen_core(tmp_path: Path) -> None:
    home = tmp_path / "home"
    clock = FakeClock()
    core = tmp_path / "ElfieNestCore"
    command = (str(core), "--port", "8002")
    port = FakeProcessPort(
        cwd=tmp_path,
        command=command,
        existence=(True, True, True, False),
        launched_pid=5109,
    )

    result = start_service(
        home,
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(),
        command=command,
        health_checker=lambda: False,
        timeout_seconds=0.1,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert isinstance(result.error, HealthCheckFailedError)
    assert port.terminations == [(5109, False)]


def test_start_cleanup_refuses_reused_pid(tmp_path: Path) -> None:
    home = tmp_path / "home"
    port = FakeProcessPort(
        cwd=tmp_path / "other",
        command=("python", "unrelated.py"),
        existence=(True, True),
        launched_pid=5108,
    )
    result = start_service(
        home,
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(),
        health_checker=lambda: False,
        timeout_seconds=0.0,
    )
    assert isinstance(result.error, CleanupFailedError)
    assert port.terminations == []


def test_start_rejects_port_collision_before_launch(tmp_path: Path) -> None:
    port = FakeProcessPort(cwd=tmp_path, ports_active=True)
    result = start_service(
        tmp_path / "home",
        tmp_path,
        process_port=port,
        recovery_lock=FakeRecoveryLock(),
        health_checker=lambda: False,
    )
    assert isinstance(result.error, ServicePortsActiveError)
    assert port.launches == []
