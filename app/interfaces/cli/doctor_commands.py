"""Local doctor diagnostics and safe auto-repair entry."""

from __future__ import annotations

from dataclasses import dataclass

from ai_runtime.lab.cli import RuntimeLab
from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_elfie_home,
    get_food_history_dir,
    get_logs_dir,
    get_model_validation_dir,
    get_runtime_locks_dir,
    get_runtime_validation_dir,
)


@dataclass(frozen=True)
class DoctorRepairReport:
    """Summary of local auto-repair actions."""

    repaired: tuple[str, ...] = ()


def run_doctor() -> int:
    """Run safe local repairs first, then offline runtime and config checks."""
    print("  🩺 Doctor diagnostics and auto-repair")
    print("  " + "=" * 45)
    print()
    try:
        repairs = repair_local_runtime_state()
        if repairs.repaired:
            print("  🔧 Auto-repaired:")
            for item in repairs.repaired:
                print(f"    - {item}")
            print()
        else:
            print("  ✅ Local structure needs no repair")
            print()
        report = RuntimeLab().run_offline_validation()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"  ❌ Doctor failed: {error}")
        return 1
    print(
        "  ✅ Repair and diagnostics complete"
        if report.passed
        else "  ⚠️  Repair complete, diagnostics found issues"
    )
    return 0 if report.passed else 1


def repair_local_runtime_state() -> DoctorRepairReport:
    """Repair local state that needs no network, keys, or user data deletion."""
    repaired: list[str] = []
    expected_dirs = (
        get_elfie_home(),
        get_elfie_home() / "assets",
        get_elfie_home() / "assets" / "users",
        get_elfie_home() / "configs",
        get_elfie_home() / "elfies",
        get_logs_dir(),
        get_food_history_dir(),
        get_model_validation_dir(),
        get_runtime_validation_dir(),
        get_runtime_locks_dir(),
    )
    missing_dirs = [path for path in expected_dirs if not path.exists()]
    ensure_elfie_home()
    if missing_dirs:
        repaired.append("Created missing ~/.elfienest data directories")

    return DoctorRepairReport(tuple(repaired))
