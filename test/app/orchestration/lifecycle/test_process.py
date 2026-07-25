from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Callable, List, Tuple

import pytest
from _pytest.monkeypatch import MonkeyPatch

from app.orchestration.lifecycle import process as service_process


def test_register_service_process_rejects_replacing_live_pid(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    elfie_home = tmp_path / "home"
    service_process.register_service_process(elfie_home, 6099)
    monkeypatch.setattr(service_process.os, "kill", lambda _pid, _signal: None)

    with pytest.raises(FileExistsError):
        service_process.register_service_process(elfie_home, 6100)

    assert (elfie_home / "elfienest.pid").read_text(encoding="utf-8") == "6099"


def test_register_service_process_reclaims_stale_pid_receipt(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    elfie_home = tmp_path / "home"
    service_process.register_service_process(elfie_home, 6099)
    monkeypatch.setattr(service_process.os, "kill", lambda _pid, _signal: (_ for _ in ()).throw(ProcessLookupError()))

    pid_path = service_process.register_service_process(elfie_home, 6100)

    assert pid_path.read_text(encoding="utf-8") == "6100"


def test_register_and_remove_service_pid_only_removes_own_receipt(
    tmp_path: Path,
) -> None:
    # Given
    elfie_home = tmp_path / "home"

    # When
    pid_path = service_process.register_service_process(elfie_home, 6101)
    service_process.remove_service_process(elfie_home, 9999)

    # Then
    assert pid_path.read_text(encoding="utf-8") == "6101"

    # When
    service_process.remove_service_process(elfie_home, 6101)

    # Then
    assert not pid_path.exists()


def test_register_current_service_uses_process_pid_and_registers_cleanup(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    elfie_home = tmp_path / "home"
    cleanups: List[Tuple[Path, int]] = []

    def record_cleanup(
        callback: Callable[[Path, int], None], home: Path, pid: int
    ) -> Callable[[Path, int], None]:
        cleanups.append((home, pid))
        return callback

    monkeypatch.setattr(service_process.os, "getpid", lambda: 6102)
    monkeypatch.setattr(service_process.atexit, "register", record_cleanup)

    # When
    pid_path = service_process.register_current_service(elfie_home)

    # Then
    assert pid_path.read_text(encoding="utf-8") == "6102"
    assert cleanups == [(elfie_home, 6102)]


def test_command_identity_rejects_serve_path_after_python_code_argument(
    tmp_path: Path,
) -> None:
    # Given
    expected_script = (tmp_path / "scripts" / "serve.py").resolve()
    command = ("python", "-c", "print('unrelated')", "scripts/serve.py")

    # When
    matches = service_process.command_runs_service(command, tmp_path, expected_script)

    # Then
    assert matches is False


def test_restart_command_preserves_custom_ports_and_drops_force() -> None:
    # Given
    command = (
        "python",
        "scripts/serve.py",
        "--fallback",
        "--force",
        "--port",
        "8100",
        "--ws-port=8866",
        "--godot-ws-port",
        "8768",
    )

    # When
    restart_command = service_process.restart_command_from_process(command)
    http_port = service_process.http_port_from_command(restart_command)

    # Then
    assert restart_command == (
        "python",
        "scripts/serve.py",
        "--fallback",
        "--port",
        "8100",
        "--ws-port=8866",
        "--godot-ws-port",
        "8768",
    )
    assert http_port == 8100
    assert service_process.service_ports_from_command(restart_command) == (
        8100,
        8768,
        8866,
    )


def test_default_service_ports_include_three_application_services() -> None:
    assert service_process.DEFAULT_SERVICE_PORTS == (8000, 8765, 8766)


def test_validate_service_ports_rejects_fixed_port_collisions() -> None:
    assert service_process.validate_service_ports(8000, 8766) is None
    assert service_process.validate_service_ports(8765, 8866) is not None


def test_validate_service_ports_rejects_out_of_range_values() -> None:
    assert service_process.validate_service_ports(0, 8766) is not None
    assert service_process.validate_service_ports(8000, 65536) is not None


def test_register_service_process_secures_elfie_home(tmp_path: Path) -> None:
    # Given
    elfie_home = tmp_path / "home"
    elfie_home.mkdir(mode=0o755)

    # When
    service_process.register_service_process(elfie_home, 6301)

    # Then
    assert stat.S_IMODE(elfie_home.stat().st_mode) == 0o700


def test_default_inspector_reads_linux_proc_without_lsof(tmp_path: Path) -> None:
    # Given
    pid = 6302
    process_dir = tmp_path / str(pid)
    process_dir.mkdir()
    expected_cwd = tmp_path / "project"
    expected_cwd.mkdir()
    os.symlink(expected_cwd, process_dir / "cwd")
    (process_dir / "cmdline").write_bytes(
        b"/usr/bin/python3\x00scripts/serve.py\x00--port\x008100\x00"
    )
    inspector = service_process.DefaultProcessInspector(proc_root=tmp_path)

    # When / Then
    assert inspector.cwd(pid) == expected_cwd
    assert inspector.command(pid) == (
        "/usr/bin/python3",
        "scripts/serve.py",
        "--port",
        "8100",
    )
