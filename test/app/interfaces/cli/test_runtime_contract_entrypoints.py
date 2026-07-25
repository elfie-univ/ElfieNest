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
    assert "完整补丁版本" in result.stderr


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
    assert "解释器版本错误" in result.stderr
    assert "CPython" in result.stderr


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
