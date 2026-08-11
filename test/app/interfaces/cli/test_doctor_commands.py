from __future__ import annotations

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli import doctor_commands
from app.orchestration.lifecycle import DoctorRepairResult, DoctorValidationResult


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
