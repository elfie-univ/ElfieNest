"""Local OS process, port, and PID receipt adapters for lifecycle workflows."""

from __future__ import annotations

import atexit
import os
import shlex
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Final, Mapping, Optional, Sequence, Tuple

from app.orchestration.lifecycle.ports import (
    LocalProcessEntry,
    ProcessInspectorPort,
    ProcessSnapshot,
)
from infrastructure.platform.lifecycle.windows_job import (
    WindowsJobObject,
    attach_process_to_job,
    deterministic_job_name,
)

PID_FILENAME: Final = "elfienest.pid"
DEFAULT_SERVICE_PORTS: Final[Tuple[int, ...]] = (8000, 8765)
DEFAULT_HTTP_PORT: Final = 8000
DEFAULT_GODOT_WS_PORT: Final = 8765
INTERNAL_SERVICE_PORTS: Final[Tuple[int, ...]] = (8765,)


class DefaultProcessInspector:
    """Read local process information through operating-system commands."""

    def __init__(self, proc_root: Optional[Path] = None) -> None:
        self._proc_root = proc_root or Path("/proc")

    def exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        state = self._state(pid)
        return state not in {"", "Z"}

    def _state(self, pid: int) -> Optional[str]:
        stat_path = self._proc_root / str(pid) / "stat"
        try:
            if stat_path.is_file():
                remainder = stat_path.read_text(encoding="utf-8").rpartition(")")[2]
                fields = remainder.split()
                return fields[0][:1] if fields else None
        except OSError:
            return None
        try:
            completed = subprocess.run(
                ["ps", "-p", str(pid), "-o", "state="],
                check=False,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        state = completed.stdout.strip()
        if completed.returncode != 0 or not state:
            return ""
        return state[:1]

    def cwd(self, pid: int) -> Path:
        process_dir = self._proc_root / str(pid)
        cwd_link = process_dir / "cwd"
        if process_dir.is_dir() and cwd_link.exists():
            return Path(os.readlink(cwd_link))
        completed = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=True,
            capture_output=True,
            text=True,
        )
        paths = [
            line[1:] for line in completed.stdout.splitlines() if line.startswith("n")
        ]
        if not paths:
            raise OSError("lsof did not return cwd")
        return Path(paths[0])

    def command(self, pid: int) -> Tuple[str, ...]:
        process_dir = self._proc_root / str(pid)
        cmdline_path = process_dir / "cmdline"
        if cmdline_path.is_file():
            return tuple(
                argument.decode(errors="surrogateescape")
                for argument in cmdline_path.read_bytes().split(b"\0")
                if argument
            )
        completed = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            check=True,
            capture_output=True,
            text=True,
        )
        return tuple(shlex.split(completed.stdout.strip()))


def command_runs_service(
    command: Sequence[str], process_cwd: Path, expected_script: Path
) -> bool:
    """Identify absolute or cwd-relative scripts/serve.py arguments."""
    for argument in command[1:]:
        if argument in ("-c", "-m"):
            return False
        if argument and not argument.startswith("-"):
            return (process_cwd / argument).resolve() == expected_script
    return False


def restart_command_from_process(command: Sequence[str]) -> Tuple[str, ...]:
    """Preserve service arguments while removing the foreground-only --force flag."""
    transient_flags = {"--force"}
    return tuple(argument for argument in command if argument not in transient_flags)


def http_port_from_command(command: Sequence[str]) -> int:
    """Read the HTTP port from a service command already validated by argparse."""
    for index, argument in enumerate(command):
        if argument.startswith("--port="):
            return int(argument.split("=", maxsplit=1)[1])
        if argument == "--port" and index + 1 < len(command):
            return int(command[index + 1])
    return DEFAULT_HTTP_PORT


def service_ports_from_command(command: Sequence[str]) -> Tuple[int, ...]:
    """Return the HTTP and Godot WebSocket ports used by a service command."""
    godot_ws_port = DEFAULT_GODOT_WS_PORT
    for index, argument in enumerate(command):
        if argument.startswith("--godot-ws-port="):
            godot_ws_port = int(argument.split("=", maxsplit=1)[1])
        elif argument == "--godot-ws-port" and index + 1 < len(command):
            godot_ws_port = int(command[index + 1])
    return (http_port_from_command(command), godot_ws_port)


def validate_service_ports(
    http_port: int,
    godot_ws_port: int = DEFAULT_GODOT_WS_PORT,
) -> str | None:
    """Validate externally configurable and fixed service ports."""
    ports = (http_port, godot_ws_port)
    if any(port < 1 or port > 65535 for port in ports):
        return "Ports must be in the 1-65535 range"
    if len(set(ports)) != len(ports):
        return "HTTP and Godot WebSocket ports must be distinct"
    return None


def any_service_port_in_use(ports: Sequence[int] = DEFAULT_SERVICE_PORTS) -> bool:
    """Return whether any default ElfieNest service port is listening."""
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                return True
    return False


def register_service_process(elfie_home: Path, pid: int) -> Path:
    """Atomically write the PID receipt for the current service process."""
    secure_elfie_home(elfie_home)
    pid_path = elfie_home / PID_FILENAME
    _reject_live_pid_replacement(pid_path, pid)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{PID_FILENAME}.", dir=str(elfie_home)
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
            receipt.write(str(pid))
        temporary_path.replace(pid_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return pid_path


def _reject_live_pid_replacement(pid_path: Path, new_pid: int) -> None:
    try:
        content = pid_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return
    try:
        recorded_pid = int(content)
    except ValueError as error:
        raise FileExistsError(
            f"Existing PID receipt is invalid; refusing to overwrite: {content!r}"
        ) from error
    if recorded_pid == new_pid:
        return
    if not DefaultProcessInspector().exists(recorded_pid):
        pid_path.unlink(missing_ok=True)
        return
    raise FileExistsError(
        f"PID {recorded_pid} is still running; refusing to overwrite service receipt"
    )


def secure_elfie_home(elfie_home: Path) -> None:
    """Ensure the local data directory is accessible only to the current system user."""
    elfie_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        elfie_home.chmod(0o700)


def register_current_service(elfie_home: Path) -> Path:
    """Register the current service process and clean up its PID receipt on normal exit."""
    pid = os.getpid()
    pid_path = register_service_process(elfie_home, pid)
    atexit.register(remove_service_process, elfie_home, pid)
    return pid_path


def remove_service_process(elfie_home: Path, pid: int) -> None:
    """Remove the PID receipt only while it still belongs to the calling process."""
    pid_path = elfie_home / PID_FILENAME
    try:
        recorded_pid = pid_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return
    if recorded_pid == str(pid):
        pid_path.unlink(missing_ok=True)


def get_port_occupant_pid(port: int) -> Optional[int]:
    """Get the PID of the process occupying a port, if any."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.2)
        if connection.connect_ex(("127.0.0.1", port)) != 0:
            return None

    try:
        completed = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        return int(completed.stdout.strip().split("\n")[0])
    except (OSError, subprocess.SubprocessError, ValueError, subprocess.TimeoutExpired):
        return None


def kill_port_occupant(
    port: int, timeout_seconds: float = 5.0
) -> Tuple[bool, Optional[str]]:
    """
    Kill the process occupying a port.

    Returns:
        Tuple of (success, error_message)
    """
    import signal
    import time

    pid = get_port_occupant_pid(port)
    if pid is None:
        return True, None

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True, None
    except PermissionError as error:
        return False, f"Permission denied: {error}"
    except OSError as error:
        return False, str(error)

    inspector = DefaultProcessInspector()
    deadline = time.monotonic() + timeout_seconds
    while inspector.exists(pid) and time.monotonic() < deadline:
        time.sleep(0.1)

    if inspector.exists(pid):
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    if inspector.exists(pid):
        return False, f"PID {pid} did not exit"
    return True, None


class LocalServiceProcessAdapter:
    """Concrete local-process implementation of the lifecycle process Port."""

    def __init__(self, inspector: Optional[ProcessInspectorPort] = None) -> None:
        self._inspector = inspector or DefaultProcessInspector()
        self._windows_jobs: dict[int, WindowsJobObject] = {}

    def exists(self, pid: int) -> bool:
        return self._inspector.exists(pid)

    def inspect(self, pid: int) -> ProcessSnapshot:
        return ProcessSnapshot(
            pid=pid,
            cwd=self._inspector.cwd(pid),
            command=self._inspector.command(pid),
        )

    def launch(
        self,
        command: Sequence[str],
        cwd: Path,
        *,
        environment: Optional[Mapping[str, str]] = None,
    ) -> int:
        child_environment = os.environ.copy()
        if environment is not None:
            child_environment.update(environment)
        if os.name == "nt":
            # Keep a distinct Windows process group so a console close cannot
            # strand a frozen Core child.  Termination below still targets the
            # complete tree rather than relying on parentage alone.
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=child_environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            job_name = child_environment.get("ELFIENEST_JOB_NAME")
            if not job_name:
                job_name = deterministic_job_name("core", str(process.pid))
            try:
                job = attach_process_to_job(process.pid, job_name)
            except Exception:
                # Popen succeeded but the ownership backstop did not.  Do not
                # return a Core that the lifecycle cannot later clean up.
                try:
                    process.kill()
                    process.wait(timeout=1.0)
                except (OSError, subprocess.SubprocessError, TimeoutError):
                    pass
                raise
            if job is not None:
                self._windows_jobs[process.pid] = job
        else:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=child_environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return process.pid

    def terminate(self, pid: int, *, force: bool = False) -> None:
        import signal

        if os.name == "nt":
            job = self._windows_jobs.get(pid)
            try:
                if force and job is not None:
                    job.terminate()
                else:
                    _terminate_windows_process_tree(pid, force=force)
            finally:
                if job is not None:
                    job.close()
                    self._windows_jobs.pop(pid, None)
            return
        requested_signal = signal.SIGKILL if force else signal.SIGTERM
        try:
            process_group = os.getpgid(pid)
        except OSError:
            os.kill(pid, requested_signal)
            return
        # LocalServiceProcessAdapter launches each managed Core with
        # start_new_session=True. Signal that exact group so a frozen PyInstaller
        # parent cannot leave its real Core child listening on the service ports.
        if process_group == pid:
            os.killpg(process_group, requested_signal)
        else:
            os.kill(pid, requested_signal)

    def ports_in_use(self, ports: Sequence[int]) -> bool:
        return any_service_port_in_use(ports)

    def port_occupant_pid(self, port: int) -> Optional[int]:
        return get_port_occupant_pid(port)

    def current_pid(self) -> int:
        return os.getpid()

    def list_processes(self) -> Tuple[LocalProcessEntry, ...]:
        completed = subprocess.run(
            ["ps", "aux"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        entries: list[LocalProcessEntry] = []
        for line in completed.stdout.splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            try:
                pid = int(parts[1])
                parent_pid = int(parts[2])
            except ValueError:
                continue
            command = tuple(parts[10].split())
            try:
                cwd = self._inspector.cwd(pid) if self._inspector.exists(pid) else None
            except (OSError, subprocess.SubprocessError):
                cwd = None
            entries.append(
                LocalProcessEntry(
                    pid=pid,
                    parent_pid=parent_pid,
                    command=command,
                    cwd=cwd,
                )
            )
        return tuple(entries)

    def read_receipt(self, elfie_home: Path) -> Optional[str]:
        try:
            return (elfie_home / PID_FILENAME).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None

    def receipt_exists(self, elfie_home: Path) -> bool:
        return (elfie_home / PID_FILENAME).is_file()

    def register_receipt(self, elfie_home: Path, pid: int) -> Path:
        return register_service_process(elfie_home, pid)

    def remove_receipt(self, elfie_home: Path, pid: int) -> None:
        remove_service_process(elfie_home, pid)

    def clear_receipt(self, elfie_home: Path) -> None:
        (elfie_home / PID_FILENAME).unlink(missing_ok=True)

    def register_current(self, elfie_home: Path) -> Path:
        return register_current_service(elfie_home)


def _terminate_windows_process_tree(pid: int, *, force: bool) -> None:
    """Terminate one validated Windows process and its descendants."""
    command = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        command.append("/F")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    # taskkill returns 128 when the target exited between identity validation
    # and the kill request.  That race is already a successful stop outcome.
    if completed.returncode not in {0, 128}:
        detail = (completed.stderr or completed.stdout).strip()
        raise OSError(
            detail or f"taskkill failed with exit code {completed.returncode}"
        )
