"""Platform-specific public Ollama command and path selection."""

from __future__ import annotations

import os
import platform as platform_module
from pathlib import Path
from typing import Literal, Tuple

PlatformName = Literal["darwin", "linux", "win32"]


def current_platform() -> PlatformName:
    """Return the one platform name used by the recorded public binding."""
    system = platform_module.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "windows":
        return "win32"
    return "linux"


def official_command(platform_name: PlatformName, script_path: Path) -> Tuple[str, ...]:
    """Return the documented interpreter for an already downloaded installer."""
    if platform_name == "win32":
        return (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        )
    return ("/bin/sh", str(script_path))


def launch_command(
    binding_platform: PlatformName, install_kind: str, launch_target: str
) -> Tuple[str, ...]:
    """Start only the target recorded in the fixed public binding."""
    if binding_platform == "darwin":
        return ("/usr/bin/open", "-a", launch_target)
    if binding_platform == "win32":
        return (launch_target,)
    if install_kind == "systemd-user":
        return ("systemctl", "--user", "start", launch_target)
    if install_kind == "systemd-system":
        return ("systemctl", "start", launch_target)
    return (launch_target, "serve")


def official_launch_target(platform_name: PlatformName) -> Tuple[str, str]:
    """Resolve only documented public Ollama installation locations."""
    if platform_name == "darwin":
        return ("/Applications/Ollama.app", "official-script")
    if platform_name == "win32":
        root = os.environ.get("LOCALAPPDATA", r"C:\\Users\\Default\\AppData\\Local")
        return (
            str(Path(root) / "Programs" / "Ollama" / "ollama.exe"),
            "official-script",
        )
    candidates = tuple(
        Path(path)
        for path in ("/usr/local/bin/ollama", "/usr/bin/ollama", "/bin/ollama")
    )
    installed = tuple(
        path for path in candidates if path.is_file() and not path.is_symlink()
    )
    if len(installed) != 1:
        raise RuntimeError("无法确定官方 Ollama 的唯一 Linux 可执行文件")
    return (str(installed[0]), "official-script")
