import os
import shutil
import stat
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_bootstrap_ensure_keeps_missing_godot_web_nonfatal(tmp_path: Path) -> None:
    """A missing optional Godot export must not stop the web service launcher."""
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(REPOSITORY_ROOT / "scripts/bootstrap.sh", scripts_dir / "bootstrap.sh")
    (project_root / ".python-version").write_text("3.9.25\n")
    (project_root / "build/web").mkdir(parents=True)
    (project_root / "build/web/manifest.json").write_text("{}\n")
    (project_root / ".venv/bin").mkdir(parents=True)
    _make_executable(project_root / ".venv/bin/python3")
    _make_executable(project_root / ".venv/bin/python")
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=prod"],
        cwd=project_root,
        env={**os.environ, "ELFIE_HOME": str(elfie_home)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Godot Web Runtime 缺失" in result.stderr
    assert "部分依赖缺失（警告）" in result.stdout
