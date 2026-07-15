from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple


class FailingInspector:
    def exists(self, pid: int) -> bool:
        raise AssertionError(f"无 PID 文件时不应检查进程 {pid}")

    def cwd(self, pid: int) -> Path:
        raise AssertionError(f"无 PID 文件时不应读取进程目录 {pid}")

    def command(self, pid: int) -> Tuple[str, ...]:
        raise AssertionError(f"无 PID 文件时不应读取进程命令 {pid}")


class FakeInspector:
    """可变 fake 用于模拟一个进程在轮询期间的存活状态。"""

    def __init__(
        self,
        *,
        cwd: Path,
        command: Sequence[str],
        existence: Sequence[bool],
    ) -> None:
        self._cwd = cwd
        self._command = tuple(command)
        self._existence = list(existence)
        self._last_existence = self._existence[-1]

    def exists(self, pid: int) -> bool:
        del pid
        if self._existence:
            self._last_existence = self._existence.pop(0)
        return self._last_existence

    def cwd(self, pid: int) -> Path:
        del pid
        return self._cwd

    def command(self, pid: int) -> Tuple[str, ...]:
        del pid
        return self._command


class FakeClock:
    """由 sleeper 推进的确定性时钟。"""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


class RecordingLauncher:
    """记录启动参数并返回固定 PID。"""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.calls: List[Tuple[Tuple[str, ...], Path]] = []

    def __call__(self, command: Sequence[str], cwd: Path) -> int:
        self.calls.append((tuple(command), cwd))
        return self.pid


def write_pid(elfie_home: Path, pid: int) -> Path:
    elfie_home.mkdir(parents=True)
    pid_path = elfie_home / "elfienest.pid"
    pid_path.write_text(str(pid), encoding="utf-8")
    return pid_path


def serve_command(project_root: Path) -> Tuple[str, ...]:
    return ("python", str((project_root / "scripts" / "serve.py").resolve()))
