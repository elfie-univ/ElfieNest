from __future__ import annotations

from app.interfaces.cli import doctor_commands


def test_doctor_repair_creates_home_dirs_without_implicit_foods(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    # When
    report = doctor_commands.repair_local_runtime_state()

    # Then
    assert (tmp_path / "validations").is_dir()
    assert "创建缺失的 ~/.elfienest 数据目录和子目录" in report.repaired
    assert not (tmp_path / "foods.yaml").exists()


def test_doctor_runs_repair_before_offline_validation(
    monkeypatch,
    capsys,
) -> None:
    # Given
    calls: list[str] = []
    monkeypatch.setattr(
        doctor_commands,
        "repair_local_runtime_state",
        lambda: calls.append("repair") or doctor_commands.DoctorRepairReport(()),
    )

    class FakeReport:
        passed = True

    class FakeRuntimeLab:
        def run_offline_validation(self):
            calls.append("validate")
            return FakeReport()

    monkeypatch.setattr(doctor_commands, "RuntimeLab", FakeRuntimeLab)

    # When
    exit_code = doctor_commands.run_doctor()

    # Then
    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls == ["repair", "validate"]
    assert "Doctor 诊断并自动修复" in output
    assert "修复与诊断完成" in output
