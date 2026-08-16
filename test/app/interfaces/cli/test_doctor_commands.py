from __future__ import annotations

from pathlib import Path

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli import doctor_commands
from app.orchestration.lifecycle import DoctorRepairResult, DoctorValidationResult
from app.orchestration.lifecycle.ports import LocalProcessEntry, ProcessSnapshot


def test_doctor_repair_creates_home_dirs_without_implicit_foods(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    # When
    report = doctor_commands.repair_local_runtime_state(create_lifecycle_facade())

    # Then
    assert (tmp_path / "reports" / "runtime-validations").is_dir()
    assert "Created missing ~/.elfienest data directories" in report.repaired
    assert not (tmp_path / "configs" / "food-packages.yaml").exists()
    retired = {"backups", "cache", "developer", "files", "models", "sessions", "skills"}
    assert retired.isdisjoint(path.name for path in tmp_path.iterdir())


def test_doctor_runs_repair_before_offline_validation(
    monkeypatch,
    capsys,
) -> None:
    # Given
    calls: list[str] = []

    class FakeLifecycle:
        def repair_local_state(self) -> DoctorRepairResult:
            calls.append("repair")
            return DoctorRepairResult()

        def run_offline_validation(self) -> DoctorValidationResult:
            calls.append("validate")
            return DoctorValidationResult(passed=True)

    # When
    exit_code = doctor_commands.run_doctor(FakeLifecycle())  # type: ignore[arg-type]

    # Then
    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls == ["repair", "validate"]
    assert "Doctor diagnostics and auto-repair" in output
    assert "Repair and diagnostics complete" in output


def test_process_discovery_uses_lifecycle_owned_service_identity() -> None:
    class FakeLifecycle:
        def current_pid(self) -> int:
            return 999

        def list_processes(self) -> tuple[LocalProcessEntry, ...]:
            return (
                LocalProcessEntry(
                    pid=42,
                    parent_pid=1,
                    command=("/managed/core", "--lan"),
                    cwd=None,
                ),
            )

        def is_managed_service_command(self, command: tuple[str, ...]) -> bool:
            return command[:1] == ("/managed/core",)

    processes = doctor_commands.find_all_elfienest_processes(FakeLifecycle())

    assert [(process.pid, process.process_type) for process in processes] == [
        (42, "python")
    ]


def test_port_fix_is_diagnostic_only_and_never_kills_an_occupant(capsys) -> None:
    class FakeLifecycle:
        def port_occupant_pid(self, port: int) -> int | None:
            assert port == 8000
            return 4242

        def inspect_process(self, pid: int) -> ProcessSnapshot:
            assert pid == 4242
            return ProcessSnapshot(
                pid, cwd=Path("/third-party"), command=("other-service",)
            )

        def process_exists(self, pid: int) -> bool:
            return pid == 4242

        def terminate_process(self, pid: int, *, force: bool = False) -> None:
            raise AssertionError(f"Doctor must not terminate PID {pid}")

    assert (
        doctor_commands.interactive_port_cleanup(
            FakeLifecycle(), ports=(8000,), force=True
        )
        is False
    )
    output = capsys.readouterr().out
    assert "diagnostic only" in output
