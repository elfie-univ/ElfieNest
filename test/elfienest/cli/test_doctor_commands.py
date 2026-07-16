from __future__ import annotations

from elfienest.cli import doctor_commands
from runtime.food.models import FIXED_FOOD_KINDS
from runtime.food.store import FoodCatalogStore


def test_doctor_repair_creates_home_dirs_and_compatibility_foods(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    # When
    report = doctor_commands.repair_local_runtime_state()

    # Then
    catalog = FoodCatalogStore().load()
    assert set(catalog.recipes) == set(FIXED_FOOD_KINDS)
    assert (tmp_path / "validations").is_dir()
    assert "创建缺失的 ~/.elfienest 数据目录和子目录" in report.repaired
    assert "补齐缺失的兼容粮食策略 foods.yaml" in report.repaired


def test_doctor_runs_repair_before_offline_validation(
    monkeypatch,
    capsys,
) -> None:
    # Given
    calls: list[str] = []
    monkeypatch.setattr(
        doctor_commands,
        "repair_local_runtime_state",
        lambda: calls.append("repair")
        or doctor_commands.DoctorRepairReport(("补齐缺失的兼容粮食策略 foods.yaml",)),
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
    assert "补齐缺失的兼容粮食策略 foods.yaml" in output
