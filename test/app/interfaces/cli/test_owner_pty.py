from __future__ import annotations

import errno
import os
import pty
import select
import signal
import time
from pathlib import Path
from typing import Final, Tuple

from app.infrastructure.persistence.store import (
    get_db,
    hash_password,
    init_db,
    verify_password,
)
from test.app.interfaces.cli.entrypoint_test_support import PROJECT_ROOT

_CHILD_CODE: Final = """
from app.interfaces.cli.owner_commands import recover_owner_interactive
raise SystemExit(recover_owner_interactive())
"""


def _create_owner_database(elfie_home: Path) -> Path:
    db_path = elfie_home / "nest.db"
    init_db(str(db_path))
    with get_db(str(db_path)) as connection:
        user_id = connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("doctor-bai", hash_password("before-reset")),
        ).lastrowid
        connection.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            ("old-session", user_id, 12345.0),
        )
        connection.commit()
    return db_path


def _spawn_reset(elfie_home: Path) -> Tuple[int, int]:
    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        environment = os.environ.copy()
        environment["ELFIE_HOME"] = str(elfie_home)
        python = str(PROJECT_ROOT / ".venv" / "bin" / "python3")
        os.execve(python, [python, "-c", _CHILD_CODE], environment)
    return child_pid, master_fd


def _read_until(master_fd: int, marker: bytes, transcript: bytearray) -> None:
    deadline = time.monotonic() + 10.0
    while marker not in transcript:
        if time.monotonic() >= deadline:
            raise AssertionError(f"PTY 未出现预期提示: {marker!r}")
        readable, _, _ = select.select([master_fd], [], [], 0.2)
        if not readable:
            continue
        transcript.extend(os.read(master_fd, 4096))


def _wait_for_child(child_pid: int, master_fd: int, transcript: bytearray) -> int:
    deadline = time.monotonic() + 10.0
    status = None
    while status is None:
        if time.monotonic() >= deadline:
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
            raise AssertionError("PTY Owner恢复命令超时")
        waited_pid, waited_status = os.waitpid(child_pid, os.WNOHANG)
        if waited_pid == child_pid:
            status = waited_status
        readable, _, _ = select.select([master_fd], [], [], 0.1)
        if readable:
            try:
                transcript.extend(os.read(master_fd, 4096))
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
    os.close(master_fd)
    return os.waitstatus_to_exitcode(status)


def _password_and_session_state(db_path: Path) -> Tuple[str, int]:
    with get_db(str(db_path)) as connection:
        password_hash = connection.execute(
            "SELECT password_hash FROM users WHERE role = 'owner'"
        ).fetchone()[0]
        session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[
            0
        ]
    return str(password_hash), int(session_count)


def test_owner_recovery_pty_hides_password_and_updates_database(tmp_path: Path) -> None:
    elfie_home = tmp_path / "home"
    db_path = _create_owner_database(elfie_home)
    new_password = "after-reset-hidden"
    transcript = bytearray()
    child_pid, master_fd = _spawn_reset(elfie_home)

    _read_until(master_fd, "New Owner username".encode(), transcript)
    os.write(master_fd, b"new-owner\n")
    _read_until(master_fd, "New Owner password".encode(), transcript)
    os.write(master_fd, f"{new_password}\n".encode())
    _read_until(master_fd, "Re-enter new Owner password".encode(), transcript)
    os.write(master_fd, f"{new_password}\n".encode())
    exit_code = _wait_for_child(child_pid, master_fd, transcript)

    password_hash, session_count = _password_and_session_state(db_path)
    output = transcript.decode(errors="replace")
    assert exit_code == 0
    assert new_password not in output
    assert verify_password("before-reset", password_hash) is False
    assert verify_password(new_password, password_hash) is True
    assert session_count == 0


def test_owner_recovery_pty_eof_keeps_database_unchanged(tmp_path: Path) -> None:
    elfie_home = tmp_path / "home"
    db_path = _create_owner_database(elfie_home)
    original_hash, original_sessions = _password_and_session_state(db_path)
    transcript = bytearray()
    child_pid, master_fd = _spawn_reset(elfie_home)

    _read_until(master_fd, "New Owner username".encode(), transcript)
    os.write(master_fd, b"new-owner\n")
    _read_until(master_fd, "New Owner password".encode(), transcript)
    os.write(master_fd, b"first-entry\n")
    _read_until(master_fd, "Re-enter new Owner password".encode(), transcript)
    os.write(master_fd, b"\x04")
    exit_code = _wait_for_child(child_pid, master_fd, transcript)

    password_hash, session_count = _password_and_session_state(db_path)
    assert exit_code == 1
    assert "first-entry" not in transcript.decode(errors="replace")
    assert password_hash == original_hash
    assert session_count == original_sessions


def test_owner_recovery_pty_ctrl_c_keeps_database_unchanged(tmp_path: Path) -> None:
    elfie_home = tmp_path / "home"
    db_path = _create_owner_database(elfie_home)
    original_hash, original_sessions = _password_and_session_state(db_path)
    transcript = bytearray()
    child_pid, master_fd = _spawn_reset(elfie_home)

    _read_until(master_fd, "New Owner username".encode(), transcript)
    os.write(master_fd, b"\x03")
    exit_code = _wait_for_child(child_pid, master_fd, transcript)

    password_hash, session_count = _password_and_session_state(db_path)
    assert exit_code == 1
    assert password_hash == original_hash
    assert session_count == original_sessions
