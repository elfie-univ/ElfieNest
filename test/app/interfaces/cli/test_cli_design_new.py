from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from test.app.interfaces.cli.entrypoint_test_support import write_executable
from test.support.paths import PROJECT_ROOT


def test_cli_help_uses_owner_and_doctor_without_old_homepage_duplicates() -> None:
    # Given / When
    environment = os.environ.copy()
    environment.pop("ELFIENEST_DESKTOP_BIN", None)
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            "scripts/elfienest.py",
            "--help",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
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
    assert "desktop" not in result.stdout


def test_packaged_cli_help_exposes_desktop_command() -> None:
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            "-c",
            (
                "import sys; from scripts import elfienest; "
                "sys.frozen = True; elfienest.main(['--help'])"
            ),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "desktop" in result.stdout


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


def test_shell_routes_command_arguments_to_the_matching_entrypoint(
    tmp_path: Path,
) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    (project_root / "pyproject.toml").write_text("", encoding="utf-8")
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
    (project_root / "pyproject.toml").write_text("# marker\n")
    (project_root / "scripts").mkdir(parents=True, exist_ok=True)
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
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

    # When: one-shot commands are forwarded directly to the Python CLI.
    for command in (("start", "--port", "8100"), ("serve",), ("v",)):
        result = subprocess.run(
            [str(project_root / "elfienest.sh"), *command],
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    # Then
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "scripts/elfienest.py start --port 8100",
        "scripts/elfienest.py serve",
        "scripts/elfienest.py version",
    ]


def _write_interactive_shell_fixture(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "ElfieNest"
    (project_root / "scripts").mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    (project_root / "pyproject.toml").write_text("# marker\n", encoding="utf-8")
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
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
    return project_root, log_path


def test_shell_without_arguments_enters_python_interactive_mode(tmp_path: Path) -> None:
    project_root, log_path = _write_interactive_shell_fixture(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(log_path),
            "TERM": "xterm",
        }
    )

    result = subprocess.run(
        [str(project_root / "elfienest.sh")],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "scripts/elfienest.py --interactive",
    ]


def test_shell_marks_direct_restart_for_concise_output(tmp_path: Path) -> None:
    project_root, log_path = _write_interactive_shell_fixture(tmp_path)
    write_executable(
        project_root / ".venv" / "bin" / "python3",
        """#!/bin/bash
if [ "${1:-}" = "-c" ]; then
    exit 0
fi
printf '%s|%s\\n' "${ELFIENEST_INTERACTIVE:-}" "$*" >> "$ENTRYPOINT_LOG"
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(log_path),
        }
    )

    result = subprocess.run(
        [str(project_root / "elfienest.sh"), "restart"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "|scripts/elfienest.py restart",
    ]


def test_shell_routes_direct_start_to_cli_entrypoint(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    (project_root / "pyproject.toml").write_text("", encoding="utf-8")
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
    (project_root / "pyproject.toml").write_text("# marker\n")
    (project_root / "scripts").mkdir(parents=True, exist_ok=True)
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
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
        "scripts/elfienest.py start --port 8100 --godot-ws-port 8768",
    ]


def test_shell_routes_direct_serve_to_supervised_cli_entrypoint(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    (project_root / "pyproject.toml").write_text("", encoding="utf-8")
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
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
        [str(project_root / "elfienest.sh"), "serve"],
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
        "scripts/elfienest.py serve",
    ]


def test_shell_routes_direct_port_flags_to_cli_parser(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    (project_root / "pyproject.toml").write_text("", encoding="utf-8")
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
    (project_root / "pyproject.toml").write_text("# marker\n")
    (project_root / "scripts").mkdir(parents=True, exist_ok=True)
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
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
        "scripts/elfienest.py --godot-ws-port 8768",
    ]
