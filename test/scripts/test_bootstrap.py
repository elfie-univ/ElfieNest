from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from test.scripts.bootstrap_test_support import (
    copy_bootstrap,
    make_executable,
    prepare_prod_runtime,
    run_bootstrap,
)
from test.support.paths import PROJECT_ROOT


def test_bootstrap_ensure_prod_fails_when_godot_web_runtime_is_missing(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_prod_runtime(project_root, godot_web=False)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=prod"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Godot Web Runtime 缺失" in result.stderr
    assert "完整产品无法启动" in result.stderr


def test_bootstrap_report_completes_in_isolated_home(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_prod_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 0, result.stderr
    assert result.stdout


def test_bootstrap_report_marks_missing_godot_as_required_failure(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_prod_runtime(project_root, godot_web=False)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["overall_state"] == "failed"
    assert report["components"]["godot_web"] == {
        "required": True,
        "state": "missing",
    }


def test_bootstrap_report_marks_absent_ollama_as_fallback(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_prod_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["components"]["ollama"] == {
        "required": False,
        "state": "fallback",
    }


def test_bootstrap_report_marks_project_ollama_as_managed(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_prod_runtime(project_root)
    make_executable(project_root / "ai_runtime/setup/bin/ollama")
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["components"]["ollama"]["state"] == "managed"


def test_bootstrap_report_marks_healthy_path_ollama_as_external(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_prod_runtime(project_root)
    fake_bin = tmp_path / "fake-bin"
    make_executable(fake_bin / "ollama")
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(
        scripts_dir,
        project_root,
        elfie_home,
        path=f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["components"]["ollama"]["state"] == "external"


def test_bootstrap_pnpm_preparation_uses_repository_pinned_version() -> None:
    bootstrap_source = (PROJECT_ROOT / "scripts/bootstrap.sh").read_text(
        encoding="utf-8"
    )
    runtime_source = (
        PROJECT_ROOT / "scripts/bootstrap_runtime_dependencies.sh"
    ).read_text(encoding="utf-8")

    assert 'PNPM_VERSION="10.12.1"' in runtime_source
    assert "pnpm@${PNPM_VERSION}" in runtime_source
    assert "pnpm@latest" not in bootstrap_source + runtime_source
