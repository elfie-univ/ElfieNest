"""ElfieNest 服务进程的本机身份、端口与 PID 收据操作。"""

from __future__ import annotations

import atexit
import os
import shlex
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Final, Optional, Protocol, Sequence, Tuple

PID_FILENAME: Final = "elfienest.pid"
DEFAULT_SERVICE_PORTS: Final[Tuple[int, ...]] = (8000, 8765, 8766)
DEFAULT_HTTP_PORT: Final = 8000
DEFAULT_GODOT_WS_PORT: Final = 8765
DEFAULT_MANAGEMENT_WS_PORT: Final = 8766
INTERNAL_SERVICE_PORTS: Final[Tuple[int, ...]] = (8765,)


class ProcessInspector(Protocol):
    """读取本地进程身份与状态所需的最小接口。"""

    def exists(self, pid: int) -> bool:
        """返回 PID 是否仍存在。"""

    def cwd(self, pid: int) -> Path:
        """返回进程当前工作目录。"""

    def command(self, pid: int) -> Tuple[str, ...]:
        """返回进程命令及参数。"""


class DefaultProcessInspector:
    """使用操作系统命令读取本地进程信息。"""

    def __init__(self, proc_root: Optional[Path] = None) -> None:
        self._proc_root = proc_root or Path("/proc")

    def exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

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
            raise OSError("lsof 未返回 cwd")
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
    """识别绝对或相对当前工作目录的 scripts/serve.py 参数。"""
    for argument in command[1:]:
        if argument in ("-c", "-m"):
            return False
        if argument and not argument.startswith("-"):
            return (process_cwd / argument).resolve() == expected_script
    return False


def restart_command_from_process(command: Sequence[str]) -> Tuple[str, ...]:
    """保留原服务参数，但移除只应由人工启动使用的 --force。"""
    transient_flags = {"--force"}
    return tuple(argument for argument in command if argument not in transient_flags)


def http_port_from_command(command: Sequence[str]) -> int:
    """从已由 argparse 验证过的服务命令中读取 HTTP 端口。"""
    for index, argument in enumerate(command):
        if argument.startswith("--port="):
            return int(argument.split("=", maxsplit=1)[1])
        if argument == "--port" and index + 1 < len(command):
            return int(command[index + 1])
    return DEFAULT_HTTP_PORT


def service_ports_from_command(command: Sequence[str]) -> Tuple[int, ...]:
    """返回当前服务命令实际使用的 HTTP、WebSocket 和固定内部端口。"""
    websocket_port = DEFAULT_MANAGEMENT_WS_PORT
    godot_ws_port = DEFAULT_GODOT_WS_PORT
    for index, argument in enumerate(command):
        if argument.startswith("--ws-port="):
            websocket_port = int(argument.split("=", maxsplit=1)[1])
        elif argument == "--ws-port" and index + 1 < len(command):
            websocket_port = int(command[index + 1])
        elif argument.startswith("--godot-ws-port="):
            godot_ws_port = int(argument.split("=", maxsplit=1)[1])
        elif argument == "--godot-ws-port" and index + 1 < len(command):
            godot_ws_port = int(command[index + 1])
    return (http_port_from_command(command), godot_ws_port, websocket_port)


def validate_service_ports(
    http_port: int,
    websocket_port: int,
    godot_ws_port: int = DEFAULT_GODOT_WS_PORT,
) -> str | None:
    """Validate externally configurable and fixed service ports."""
    ports = (http_port, websocket_port, godot_ws_port)
    if any(port < 1 or port > 65535 for port in ports):
        return "端口必须在 1-65535 范围内"
    if len(set(ports)) != len(ports):
        return "HTTP、管理 WebSocket 和 Godot WebSocket 端口不能重复"
    return None


def any_service_port_in_use(ports: Sequence[int] = DEFAULT_SERVICE_PORTS) -> bool:
    """返回任一 ElfieNest 默认服务端口是否正在监听。"""
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                return True
    return False


def register_service_process(elfie_home: Path, pid: int) -> Path:
    """原子写入当前服务进程的 PID 收据。"""
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
        raise FileExistsError(f"现有 PID 收据无效，拒绝覆盖: {content!r}") from error
    if recorded_pid == new_pid:
        return
    try:
        os.kill(recorded_pid, 0)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise FileExistsError(f"PID {recorded_pid} 状态不可验证，拒绝覆盖") from error
    raise FileExistsError(f"PID {recorded_pid} 仍在运行，拒绝覆盖服务收据")


def secure_elfie_home(elfie_home: Path) -> None:
    """确保本地数据目录仅当前系统用户可访问。"""
    elfie_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        elfie_home.chmod(0o700)


def register_current_service(elfie_home: Path) -> Path:
    """登记当前服务进程，并在正常退出时清理自己的 PID 收据。"""
    pid = os.getpid()
    pid_path = register_service_process(elfie_home, pid)
    atexit.register(remove_service_process, elfie_home, pid)
    return pid_path


def remove_service_process(elfie_home: Path, pid: int) -> None:
    """仅在 PID 收据仍属于调用进程时删除它。"""
    pid_path = elfie_home / PID_FILENAME
    try:
        recorded_pid = pid_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return
    if recorded_pid == str(pid):
        pid_path.unlink(missing_ok=True)
