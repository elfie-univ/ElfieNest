from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test.app.interfaces.cli.entrypoint_test_support import PROJECT_ROOT, write_executable


def test_system_entrypoint_files_use_elfienest_name() -> None:
    # Given
    expected_files = (
        PROJECT_ROOT / "elfienest.sh",
        PROJECT_ROOT / "scripts" / "elfienest.py",
    )

    # When
    existing_files = tuple(path.is_file() for path in expected_files)

    # Then
    assert existing_files == (True, True)
    assert not (PROJECT_ROOT / "elfie.sh").exists()
    assert not (PROJECT_ROOT / "scripts" / "elfie.py").exists()


def test_python_cli_is_internal_and_not_directly_executable() -> None:
    # Given
    python_cli = PROJECT_ROOT / "scripts" / "elfienest.py"

    # When
    is_executable = os.access(python_cli, os.X_OK)
    first_line = python_cli.read_text(encoding="utf-8").splitlines()[0]

    # Then
    assert not is_executable
    assert not first_line.startswith("#!")


def test_python_cli_rejects_non_pinned_interpreter() -> None:
    # Given
    system_python = shutil.which("python3")
    if system_python is None:
        pytest.skip("No system python3 is available for the rejection check")
    probe = subprocess.run(
        [
            system_python,
            "-c",
            "import platform,sys;print(sys.implementation.name,platform.python_version())",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.stdout.strip() == "cpython 3.9.25":
        pytest.skip("System python already matches the pinned interpreter")

    # When
    result = subprocess.run(
        [system_python, str(PROJECT_ROOT / "scripts" / "elfienest.py"), "version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode != 0
    assert "CPython 3.9.25" in result.stderr


def test_elfienest_entrypoint_dispatches_cli_to_elfienest_script(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")

    invocation_log = tmp_path / "invocation.log"
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        """#!/bin/bash
if [ "${1:-}" = "-c" ]; then
    exit 0
fi
printf '%s\n' "$*" > "$ENTRYPOINT_LOG"
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(invocation_log),
        }
    )

    # When
    result = subprocess.run(
        [str(project_root / "elfienest.sh"), "version"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode == 0, result.stdout + result.stderr
    assert invocation_log.read_text(encoding="utf-8").strip() == (
        "scripts/elfienest.py version"
    )


def test_existing_cli_help_keeps_setup_and_database_commands() -> None:
    # Given
    python_cli = PROJECT_ROOT / "scripts" / "elfienest.py"

    # When
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "bin" / "python3"), str(python_cli), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode == 0
    assert "setup" in result.stdout
    assert "db" in result.stdout
