"""统一入口启动 Lab 前，安全回收同一工作区的默认实例。"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from devtools.entrypoint import DeveloperTool


@dataclass(frozen=True)
class ForeignPortOwnerError(RuntimeError):
    """默认端口属于不应由 Lab 启动器终止的进程。"""

    port: int
    command: tuple[str, ...]

    def __str__(self) -> str:
        command_text = shlex.join(self.command) or "<无法读取命令>"
        return (
            f"默认端口 {self.port} 已被其他进程占用，未自动终止：{command_text}。"
            "请停止该进程，或显式使用 --port 启动独立 Lab。"
        )


@dataclass(frozen=True)
class RestartTimeoutError(RuntimeError):
    """已请求旧 Lab 退出，但其端口未能在限制时间内释放。"""

    ports: tuple[int, ...]

    def __str__(self) -> str:
        formatted_ports = ", ".join(str(port) for port in self.ports)
        return f"旧 Lab 未在限定时间内释放端口 {formatted_ports}，请稍后重试。"


class RestartInspector(Protocol):
    """读取并回收本机监听进程的最小边界。"""

    def listening_pids(self, port: int) -> tuple[int, ...]:
        """返回正在监听指定端口的进程。"""

    def command(self, pid: int) -> tuple[str, ...]:
        """返回进程命令行。"""

    def cwd(self, pid: int) -> Path:
        """返回进程工作目录。"""

    def terminate(self, pid: int) -> None:
        """请求进程正常退出。"""

    def wait_until_free(self, ports: tuple[int, ...]) -> bool:
        """等待所有端口不再监听。"""


class DefaultRestartInspector:
    """通过 macOS/Linux 的 lsof 和 ps 检查本机 Lab 进程。"""

    def listening_pids(self, port: int) -> tuple[int, ...]:
        completed = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
        )
        return tuple(
            sorted(
                int(line)
                for line in completed.stdout.splitlines()
                if line.strip().isdigit()
            )
        )

    def command(self, pid: int) -> tuple[str, ...]:
        completed = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            check=True,
            capture_output=True,
            text=True,
        )
        return tuple(shlex.split(completed.stdout.strip()))

    def cwd(self, pid: int) -> Path:
        completed = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=True,
            capture_output=True,
            text=True,
        )
        paths = tuple(
            Path(line[1:])
            for line in completed.stdout.splitlines()
            if line.startswith("n")
        )
        if not paths:
            raise OSError(f"无法读取进程 {pid} 的工作目录")
        return paths[0]

    def terminate(self, pid: int) -> None:
        os.kill(pid, signal.SIGTERM)

    def wait_until_free(self, ports: tuple[int, ...]) -> bool:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not any(self.listening_pids(port) for port in ports):
                return True
            time.sleep(0.05)
        return not any(self.listening_pids(port) for port in ports)


def default_lab_ports(tool: DeveloperTool) -> tuple[int, ...]:
    """Return the default web port(s) for a web Lab."""
    if tool.default_port is None:
        return ()
    # All three Developer Tool commands now launch the same HTTP service.  A
    # Nest surface still owns one internal Godot WebSocket listener directly
    # beside the HTTP port, so the default restart releases both listeners.
    return (tool.default_port, tool.default_port + 1)


def restart_default_lab(
    tool: DeveloperTool,
    workspace: Path,
    inspector: RestartInspector | None = None,
) -> None:
    """终止同一工作区、同一 Lab 的默认实例，并等待端口释放。"""
    ports = default_lab_ports(tool)
    if not ports:
        return
    active_inspector = inspector or DefaultRestartInspector()
    owners = {pid for port in ports for pid in active_inspector.listening_pids(port)}
    expected_workspace = workspace.resolve()
    for pid in owners:
        command = active_inspector.command(pid)
        if not _is_current_lab_process(
            command,
            active_inspector.cwd(pid),
            expected_workspace,
            tool.name,
        ):
            raise ForeignPortOwnerError(
                port=_first_owned_port(pid, ports, active_inspector), command=command
            )
    for pid in owners:
        active_inspector.terminate(pid)
    if owners and not active_inspector.wait_until_free(ports):
        raise RestartTimeoutError(ports=ports)


def _first_owned_port(
    pid: int, ports: tuple[int, ...], inspector: RestartInspector
) -> int:
    """返回某个进程占用的首个 Lab 端口。"""
    for port in ports:
        if pid in inspector.listening_pids(port):
            return port
    return ports[0]


def _is_current_lab_process(
    command: tuple[str, ...],
    process_cwd: Path,
    workspace: Path,
    tool_name: str,
) -> bool:
    """仅接受通过当前工作区统一入口启动的同类 Lab。"""
    expected_tools = {"elfie-lab", "nest-lab", "brain-eval"}
    if tool_name not in expected_tools:
        expected_tools = {tool_name}
    return process_cwd.resolve() == workspace and any(
        command[index : index + 3] == ("-m", "devtools", candidate)
        for index in range(len(command) - 2)
        for candidate in expected_tools
    )
