from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from test.app.interfaces.cli.entrypoint_test_support import write_executable
from test.support.paths import PROJECT_ROOT


def _copy_runtime_entrypoint_fixture(project_root: Path) -> None:
    project_root.mkdir()
    for relative_path in ("elfienest.sh", "developer.sh", ".python-version"):
        shutil.copy2(PROJECT_ROOT / relative_path, project_root / relative_path)
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(
        PROJECT_ROOT / "scripts" / "bootstrap.sh", scripts_dir / "bootstrap.sh"
    )
    shutil.copy2(
        PROJECT_ROOT / "scripts" / "bootstrap_report.sh",
        scripts_dir / "bootstrap_report.sh",
    )
    shutil.copy2(
        PROJECT_ROOT / "scripts" / "bootstrap_runtime_dependencies.sh",
        scripts_dir / "bootstrap_runtime_dependencies.sh",
    )
    (scripts_dir / "serve.py").write_text("", encoding="utf-8")
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")


def test_elfienest_entrypoint_rejects_malformed_python_version_file(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    _copy_runtime_entrypoint_fixture(project_root)
    (project_root / ".python-version").write_text("3.9\n", encoding="utf-8")

    # When
    result = subprocess.run(
        [str(project_root / "elfienest.sh"), "version"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode != 0
    assert ".python-version" in result.stderr
    assert "full Python 3.9 patch version" in result.stderr


def test_elfienest_entrypoint_rejects_wrong_venv_interpreter(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    _copy_runtime_entrypoint_fixture(project_root)
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        "#!/bin/bash\nexit 1\n",
    )
    environment = os.environ.copy()
    environment["ELFIENEST_SKIP_AUTO_REPAIR"] = "1"

    # When
    result = subprocess.run(
        [str(project_root / "elfienest.sh"), "version"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )

    # Then
    assert result.returncode != 0
    assert "Dependency installation failed" in result.stderr


def test_developer_entrypoint_rejects_external_python_override(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    _copy_runtime_entrypoint_fixture(project_root)
    external_python = tmp_path / "external-python"
    write_executable(external_python, "#!/bin/bash\nexit 0\n")
    environment = os.environ.copy()
    environment["ELFIENEST_PYTHON"] = str(external_python)

    # When
    result = subprocess.run(
        [str(project_root / "developer.sh"), "--help"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode != 0
    assert "ELFIENEST_PYTHON" in result.stderr
    assert "CPython 3.9.25" in result.stderr


def test_packaged_entrypoint_runs_bundled_core_without_bootstrap(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    invocation_log = tmp_path / "packaged-entrypoint.log"
    write_executable(
        project_root / "resources" / "python-core" / "ElfieNestCore",
        "#!/bin/bash\n"
        'printf \'%s\\n%s\\n\' "$ELFIENEST_RUNTIME_MODE" "$*" > "$ENTRYPOINT_LOG"\n',
    )
    environment = os.environ.copy()
    environment["ENTRYPOINT_LOG"] = str(invocation_log)

    # When
    result = subprocess.run(
        [str(project_root / "elfienest.sh"), "version"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert invocation_log.read_text(encoding="utf-8").splitlines() == [
        "release",
        "version",
    ]


def test_source_entrypoint_exports_worktree_runtime_context(tmp_path: Path) -> None:
    """Given 源码入口，When 分发命令，Then 子进程收到 development 与 worktree 根。"""
    project_root = tmp_path / "ElfieNest"
    _copy_runtime_entrypoint_fixture(project_root)
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
    invocation_log = tmp_path / "source-entrypoint.log"
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        "#!/bin/bash\n"
        'printf \'%s\\n%s\\n\' "$ELFIENEST_RUNTIME_MODE" "$ELFIENEST_SOURCE_ROOT" > "$ENTRYPOINT_LOG"\n',
    )
    environment = os.environ.copy()
    environment["ENTRYPOINT_LOG"] = str(invocation_log)

    result = subprocess.run(
        [str(project_root / "elfienest.sh"), "version"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert invocation_log.read_text(encoding="utf-8").splitlines() == [
        "development",
        str(project_root),
    ]
