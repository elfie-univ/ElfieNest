from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from test.support.paths import PROJECT_ROOT


def make_executable(path: Path, content: str = "#!/bin/sh\nexit 0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def copy_bootstrap(project_root: Path) -> Path:
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    for filename in (
        "bootstrap.sh",
        "bootstrap_report.sh",
        "bootstrap_runtime_dependencies.sh",
    ):
        shutil.copy2(PROJECT_ROOT / "scripts" / filename, scripts_dir / filename)
    return scripts_dir


def prepare_prod_runtime(project_root: Path, *, godot_web: bool = True) -> None:
    (project_root / ".python-version").write_text("3.9.25\n", encoding="utf-8")
    (project_root / "build/web").mkdir(parents=True)
    (project_root / "build/web/manifest.json").write_text("{}\n", encoding="utf-8")
    if godot_web:
        for suffix in ("html", "js", "wasm", "pck"):
            runtime_file = (
                project_root / "build/components/godot-web" / f"elfienest.{suffix}"
            )
            runtime_file.parent.mkdir(parents=True, exist_ok=True)
            runtime_file.write_text("runtime\n", encoding="utf-8")
    make_executable(project_root / ".venv/bin/python3")
    make_executable(project_root / ".venv/bin/python")


def run_bootstrap(
    scripts_dir: Path,
    project_root: Path,
    elfie_home: Path,
    *,
    path: str = "/usr/bin:/bin:/usr/sbin:/sbin",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "report", "--tier=prod"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "HOME": str(elfie_home.parent / "home"),
            "PATH": path,
        },
        capture_output=True,
        text=True,
        check=False,
    )
