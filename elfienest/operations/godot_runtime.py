"""本机 Godot Runtime 的启动和停止管理。"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Optional


def find_runtime_binary(project_root: Path) -> Optional[Path]:
    """只查找已导出的 ElfieNest Runtime，不查找 Godot 编辑器。"""
    candidates: list[Path] = []
    configured = os.environ.get("ELFIENEST_RUNTIME_BIN", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            project_root / ".elfienest" / "runtime" / "ElfieNestRuntime",
            project_root / "runtime" / "bin" / "ElfieNestRuntime",
            project_root / "dist" / "ElfieNestRuntime",
        ]
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def start_godot_runtime(project_root: Path, ws_port: int) -> Optional[subprocess.Popen]:
    """启动已导出的后台 Runtime；开发编辑器永远不在服务启动路径中。"""
    if os.environ.get("ELFIENEST_DISABLE_GODOT_AUTOSTART") == "1":
        return None
    binary = find_runtime_binary(project_root)
    if binary is None:
        return None
    environment = os.environ.copy()
    environment["ELFIENEST_GODOT_WS"] = f"ws://127.0.0.1:{ws_port}"
    try:
        return subprocess.Popen(
            [str(binary)],
            cwd=str(project_root),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def stop_godot_runtime(process: Optional[subprocess.Popen]) -> None:
    """停止本次服务启动的 Godot 进程，不触碰用户手工打开的实例。"""
    if process is None or process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5.0)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            return
