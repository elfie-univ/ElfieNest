"""本地 Doctor 诊断与安全自动修复入口。"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.lab.cli import RuntimeLab
from runtime.storage.data_home import (
    ensure_elfie_home,
    get_audio_cache_dir,
    get_cache_dir,
    get_elfie_home,
    get_food_history_dir,
    get_local_files_dir,
    get_logs_dir,
    get_sessions_dir,
    get_skills_dir,
    get_validation_dir,
)


@dataclass(frozen=True)
class DoctorRepairReport:
    """Doctor 本地自动修复动作摘要。"""

    repaired: tuple[str, ...] = ()


def run_doctor() -> int:
    """先执行安全本地修复，再运行不访问网络的 Runtime 与工具配置检查。"""
    print("  🩺 Doctor 诊断并自动修复")
    print("  " + "=" * 45)
    print()
    try:
        repairs = repair_local_runtime_state()
        if repairs.repaired:
            print("  🔧 已自动修复:")
            for item in repairs.repaired:
                print(f"    - {item}")
            print()
        else:
            print("  ✅ 本地结构无需修复")
            print()
        report = RuntimeLab().run_offline_validation()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"  ❌ Doctor 失败: {error}")
        return 1
    print("  ✅ 修复与诊断完成" if report.passed else "  ⚠️  修复完成，诊断仍发现问题")
    return 0 if report.passed else 1


def repair_local_runtime_state() -> DoctorRepairReport:
    """修复不需要联网、不需要密钥、不会破坏用户数据的本地状态。"""
    repaired: list[str] = []
    expected_dirs = (
        get_elfie_home(),
        get_elfie_home() / "elfies",
        get_cache_dir(),
        get_logs_dir(),
        get_skills_dir(),
        get_audio_cache_dir(),
        get_sessions_dir(),
        get_food_history_dir(),
        get_validation_dir(),
        get_local_files_dir(),
    )
    missing_dirs = [path for path in expected_dirs if not path.exists()]
    ensure_elfie_home()
    if missing_dirs:
        repaired.append("创建缺失的 ~/.elfienest 数据目录和子目录")

    return DoctorRepairReport(tuple(repaired))
