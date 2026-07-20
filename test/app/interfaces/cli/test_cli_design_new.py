from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from test.app.interfaces.cli.entrypoint_test_support import write_executable

from test.support.paths import PROJECT_ROOT


def test_cli_help_uses_owner_and_doctor_without_old_homepage_duplicates() -> None:
    # Given / When
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "bin" / "python3"), "scripts/elfienest.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode == 0
    assert "owner" in result.stdout
    assert "doctor" in result.stdout
    assert "session" not in result.stdout
    assert "stats" not in result.stdout


def test_cli_rejects_owner_secret_without_echoing_the_secret() -> None:
    # Given
    secret = "owner-secret-that-must-not-echo"

    # When
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            "scripts/elfienest.py",
            "owner",
            "--password",
            secret,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then
    assert result.returncode == 2
    assert secret not in result.stderr


def test_shell_routes_command_arguments_to_the_matching_entrypoint(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
    log_path = tmp_path / "invocations.log"
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        """#!/bin/bash
if [ "${1:-}" = "-c" ]; then
    exit 0
fi
printf '%s\n' "$*" >> "$ENTRYPOINT_LOG"
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(log_path),
            "TERM": "xterm",
        }
    )

    # When
    result = subprocess.run(
        [str(project_root / "elfienest.sh")],
        cwd=project_root,
        env=environment,
        input="start --port 8100\nserve --fallback\nexit\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    # Then
    assert result.returncode == 0
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "scripts/elfienest.py start --port 8100",
        "scripts/serve.py --fallback",
    ]


def test_shell_routes_direct_start_to_cli_entrypoint(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
    log_path = tmp_path / "invocations.log"
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        """#!/bin/bash
if [ "${1:-}" = "-c" ]; then
    exit 0
fi
printf '%s\\n' "$*" >> "$ENTRYPOINT_LOG"
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(log_path),
        }
    )

    # When
    result = subprocess.run(
        [
            str(project_root / "elfienest.sh"),
            "start",
            "--port",
            "8100",
            "--godot-ws-port",
            "8768",
            "--audio-port",
            "8769",
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    # Then
    assert result.returncode == 0
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "scripts/elfienest.py start --port 8100 --godot-ws-port 8768 --audio-port 8769",
    ]


def test_shell_routes_direct_port_flags_to_cli_parser(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
    log_path = tmp_path / "invocations.log"
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        """#!/bin/bash
if [ "${1:-}" = "-c" ]; then
    exit 0
fi
printf '%s\\n' "$*" >> "$ENTRYPOINT_LOG"
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(log_path),
        }
    )

    # When
    result = subprocess.run(
        [
            str(project_root / "elfienest.sh"),
            "--audio-port",
            "8769",
            "--godot-ws-port",
            "8768",
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    # Then
    assert result.returncode == 0
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "scripts/elfienest.py --audio-port 8769 --godot-ws-port 8768",
    ]
