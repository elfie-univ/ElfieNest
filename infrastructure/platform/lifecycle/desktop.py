"""Packaged Desktop executable, process and PID-receipt adapter."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Optional, Sequence, cast

from app.orchestration.lifecycle.ports import DesktopProcess

PID_NAME = "desktop.pid"


class LocalDesktopHostAdapter:
    """Local operating-system implementation of the Desktop host Port."""

    def find_executable(self, project_root: Path) -> Optional[Path]:
        configured = os.environ.get("ELFIENEST_DESKTOP_BIN", "").strip()
        candidates = [Path(configured).expanduser()] if configured else []
        candidates.extend(
            [
                project_root / ".elfienest" / "runtime" / "ElfieNestDesktop",
                project_root / "dist" / "ElfieNestDesktop",
                project_root
                / "dist"
                / "ElfieNest.app"
                / "Contents"
                / "MacOS"
                / "ElfieNest",
                project_root / "dist" / "win-unpacked" / "ElfieNest.exe",
                project_root / "dist" / "linux-unpacked" / "elfienest",
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

    def launch(self, command: Sequence[str], cwd: Path) -> DesktopProcess:
        console = None
        if os.environ.get("ELFIENEST_RUNTIME_MODE") == "release":
            smoke_home = os.environ.get("ELFIE_HOME", "").strip()
            if smoke_home:
                console_path = (
                    Path(smoke_home) / "logs" / "desktop-controller-console.log"
                )
                try:
                    console_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    console = console_path.open("ab")
                except OSError:
                    console = None
        try:
            process = subprocess.Popen(
                list(command),
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=console if console is not None else subprocess.DEVNULL,
                stderr=(
                    subprocess.STDOUT if console is not None else subprocess.DEVNULL
                ),
                start_new_session=True,
            )
        except BaseException:
            if console is not None:
                console.close()
            raise
        if console is not None:
            console.close()
        return cast(DesktopProcess, process)

    def process_id(self, elfie_home: Path) -> Optional[int]:
        pid_path = self._pid_path(elfie_home, create=False)
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, OSError, ValueError):
            pid = None
        if pid is None or not self.exists(pid):
            pid_path.unlink(missing_ok=True)
            return None
        return pid

    def write_receipt(self, elfie_home: Path, pid: int) -> None:
        pid_path = self._pid_path(elfie_home)
        pid_path.write_text(str(pid), encoding="utf-8")
        if os.name != "nt":
            pid_path.chmod(0o600)

    def remove_receipt(self, elfie_home: Path) -> None:
        self._pid_path(elfie_home, create=False).unlink(missing_ok=True)

    def exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def terminate(self, process: DesktopProcess, *, force: bool = False) -> None:
        if process.poll() is not None:
            return
        if force:
            cast(subprocess.Popen[bytes], process).kill()
            return
        cast(subprocess.Popen[bytes], process).terminate()

    def wait(self, process: DesktopProcess, *, timeout_seconds: float) -> None:
        try:
            cast(subprocess.Popen[bytes], process).wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError from error

    def terminate_pid(self, pid: int) -> None:
        os.kill(pid, signal.SIGTERM)

    @staticmethod
    def _pid_path(elfie_home: Path, *, create: bool = True) -> Path:
        runtime_dir = elfie_home / "runtime"
        if create:
            runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return runtime_dir / PID_NAME
