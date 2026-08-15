from __future__ import annotations

import errno
import os
import pty
import select
import shutil
import signal
import subprocess
import time
from pathlib import Path

from test.app.interfaces.cli.entrypoint_test_support import write_executable
from test.support.paths import PROJECT_ROOT


def test_cli_help_uses_owner_and_doctor_without_old_homepage_duplicates() -> None:
    # Given / When
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
            "scripts/elfienest.py",
            "--help",
        ],
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
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
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

    # When
    result = subprocess.run(
        [str(project_root / "elfienest.sh")],
        cwd=project_root,
        env=environment,
        input="start --port 8100\nserve\nv\nexit\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    # Then
    assert result.returncode == 0
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


def _read_pty_until_count(
    master_fd: int, marker: bytes, transcript: bytearray, count: int
) -> None:
    deadline = time.monotonic() + 10.0
    while transcript.count(marker) < count:
        if time.monotonic() >= deadline:
            raise AssertionError(f"PTY did not see {count} occurrences of {marker!r}")
        readable, _, _ = select.select([master_fd], [], [], 0.2)
        if readable:
            try:
                transcript.extend(os.read(master_fd, 4096))
            except OSError as error:
                if error.errno != errno.EIO:
                    raise


def _spawn_interactive_shell(project_root: Path, elfie_home: Path) -> tuple[int, int]:
    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        environment = os.environ.copy()
        environment.update(
            {
                "ELFIE_HOME": str(elfie_home),
                "ENTRYPOINT_LOG": str(elfie_home.parent / "invocations.log"),
                "TERM": "xterm",
            }
        )
        shell = str(project_root / "elfienest.sh")
        os.execve(shell, [shell], environment)
    return child_pid, master_fd


def _finish_interactive_shell(child_pid: int, master_fd: int) -> int:
    deadline = time.monotonic() + 10.0
    status: int | None = None
    while status is None:
        if time.monotonic() >= deadline:
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
            raise AssertionError("interactive shell timed out")
        waited_pid, waited_status = os.waitpid(child_pid, os.WNOHANG)
        if waited_pid == child_pid:
            status = waited_status
        readable, _, _ = select.select([master_fd], [], [], 0.1)
        if readable:
            try:
                os.read(master_fd, 4096)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
    os.close(master_fd)
    return os.waitstatus_to_exitcode(status)


def test_interactive_shell_owns_prompt_and_recalls_recent_commands(
    tmp_path: Path,
) -> None:
    project_root, log_path = _write_interactive_shell_fixture(tmp_path)

    elfie_home = tmp_path / "home"
    transcript = bytearray()
    child_pid, master_fd = _spawn_interactive_shell(project_root, elfie_home)
    try:
        _read_pty_until_count(master_fd, b"elfienest> ", transcript, 3)
        before_control = len(transcript)
        os.write(master_fd, b"discard-me\x15start\n")
        _read_pty_until_count(master_fd, b"elfienest> ", transcript, 4)
        assert b"elfienest> " in transcript[before_control:]

        os.write(master_fd, b"stop\n")
        _read_pty_until_count(master_fd, b"elfienest> ", transcript, 5)
        os.write(master_fd, b"\x1b[A\x1b[A\x1b[B\n")
        _read_pty_until_count(master_fd, b"elfienest> ", transcript, 6)
        os.write(master_fd, b"owner --password do-not-store\n")
        _read_pty_until_count(master_fd, b"elfienest> ", transcript, 7)
        os.write(master_fd, b"exit\n")
        exit_code = _finish_interactive_shell(child_pid, master_fd)
    except BaseException:
        try:
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
        except (OSError, ChildProcessError):
            pass
        os.close(master_fd)
        raise

    assert exit_code == 0
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "scripts/elfienest.py start",
        "scripts/elfienest.py stop",
        "scripts/elfienest.py stop",
        "scripts/elfienest.py owner --password do-not-store",
    ]
    assert "do-not-store" not in (elfie_home / ".cli_history").read_text(
        encoding="utf-8"
    )


def test_interactive_history_replaces_legacy_entries(tmp_path: Path) -> None:
    project_root, log_path = _write_interactive_shell_fixture(tmp_path)
    elfie_home = tmp_path / "home"
    elfie_home.mkdir()
    (elfie_home / ".cli_history").write_text(
        "owner --password legacy-secret\nstart\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ELFIE_HOME": str(elfie_home),
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(log_path),
            "TERM": "xterm",
        }
    )

    result = subprocess.run(
        [str(project_root / "elfienest.sh")],
        cwd=project_root,
        env=environment,
        input="exit\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert (elfie_home / ".cli_history").read_text(encoding="utf-8") == "exit\n"


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
        "1|scripts/elfienest.py restart",
    ]


def test_interactive_history_does_not_follow_a_symlink(tmp_path: Path) -> None:
    project_root, log_path = _write_interactive_shell_fixture(tmp_path)
    elfie_home = tmp_path / "home"
    elfie_home.mkdir()
    target = tmp_path / "outside-history"
    target.write_text("keep this file\n", encoding="utf-8")
    (elfie_home / ".cli_history").symlink_to(target)
    environment = os.environ.copy()
    environment.update(
        {
            "ELFIE_HOME": str(elfie_home),
            "ELFIENEST_SKIP_AUTO_REPAIR": "1",
            "ENTRYPOINT_LOG": str(log_path),
            "TERM": "xterm",
        }
    )

    result = subprocess.run(
        [str(project_root / "elfienest.sh")],
        cwd=project_root,
        env=environment,
        input="exit\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert target.read_text(encoding="utf-8") == "keep this file\n"
    assert (elfie_home / ".cli_history").is_symlink()


def test_shell_routes_direct_start_to_cli_entrypoint(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "elfienest.sh", project_root / "elfienest.sh")
    shutil.copy2(PROJECT_ROOT / ".python-version", project_root / ".python-version")
    (project_root / "pyproject.toml").write_text("", encoding="utf-8")
    write_executable(project_root / "scripts" / "bootstrap.sh", "#!/bin/bash\nexit 0\n")
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
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
    write_executable(project_root / "install.sh", "#!/bin/bash\nexit 1\n")
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
