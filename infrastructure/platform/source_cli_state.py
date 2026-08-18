"""Non-authoritative state for a source checkout's interactive CLI.

The files in ``.elfienest-cli.local`` are convenience state only.  They never
select a task by themselves and contain no PID, port, endpoint, credential or
active-root pointer.
"""

from __future__ import annotations

import json
import os
import shlex
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Tuple

from app.orchestration.lifecycle.ports import SourceCliCandidate

try:  # pragma: no cover - the fallback is exercised on Windows only.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


CONTROL_DIR_NAME = ".elfienest-cli.local"
HISTORY_FILE_NAME = "history"
CANDIDATE_FILE_NAME = "data-homes.json"
MAX_HISTORY_ENTRIES = 50
MAX_CANDIDATES = 64


class SourceCliStateError(OSError):
    """The optional source CLI state cannot be safely read or written."""


class SourceCliState:
    """Read and atomically update checkout-scoped convenience state."""

    def __init__(self, source_root: Path) -> None:
        self.source_root = source_root.expanduser().resolve(strict=False)
        self.control_dir = self.source_root / CONTROL_DIR_NAME
        self.history_path = self.control_dir / HISTORY_FILE_NAME
        self.candidate_path = self.control_dir / CANDIDATE_FILE_NAME
        self.lock_path = self.control_dir / ".lock"

    def load_history(self) -> Tuple[str, ...]:
        if not self._safe_existing_file(self.history_path):
            return ()
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise SourceCliStateError(
                f"无法读取源码 CLI history: {self.history_path}: {error}"
            ) from error
        return tuple(line for line in lines[-MAX_HISTORY_ENTRIES:] if line.strip())

    def record_history(self, command_line: str) -> bool:
        """Persist a harmless command; return False for sensitive input."""

        if not _safe_history_command(command_line):
            return False
        with self._locked_state():
            history = list(self.load_history())
            if history and history[-1] == command_line:
                return True
            history.append(command_line)
            self._atomic_write_text(
                self.history_path,
                "".join(f"{line}\n" for line in history[-MAX_HISTORY_ENTRIES:]),
            )
        return True

    def load_candidates(self) -> Tuple[SourceCliCandidate, ...]:
        if not self._safe_existing_file(self.candidate_path):
            return ()
        try:
            payload = json.loads(self.candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SourceCliStateError(
                f"无法读取源码 CLI 候选目录: {self.candidate_path}: {error}"
            ) from error
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise SourceCliStateError(
                f"源码 CLI 候选目录版本无效: {self.candidate_path}"
            )
        raw_candidates = payload.get("homes", [])
        if not isinstance(raw_candidates, list):
            raise SourceCliStateError(
                f"源码 CLI 候选目录格式无效: {self.candidate_path}"
            )
        result: List[SourceCliCandidate] = []
        seen: set[Path] = set()
        for item in raw_candidates[:MAX_CANDIDATES]:
            if not isinstance(item, dict) or not isinstance(item.get("home"), str):
                continue
            home = Path(item["home"]).expanduser().resolve(strict=False)
            if home in seen:
                continue
            seen.add(home)
            detail = item.get("detail", "")
            result.append(
                SourceCliCandidate(home, detail if isinstance(detail, str) else "")
            )
        return tuple(result)

    def record_candidate(self, home: Path, *, detail: str = "") -> None:
        """Add one observed root to the discovery catalog, never as active state."""

        canonical = home.expanduser().resolve(strict=False)
        with self._locked_state():
            entries = list(self.load_candidates())
            entries = [entry for entry in entries if entry.home != canonical]
            entries.insert(0, SourceCliCandidate(canonical, detail))
            payload = {
                "version": 1,
                "homes": [
                    {"home": str(entry.home), "detail": entry.detail}
                    for entry in entries[:MAX_CANDIDATES]
                ],
            }
            self._atomic_write_text(
                self.candidate_path,
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            )

    @contextmanager
    def _locked_state(self) -> Iterator[None]:
        self._ensure_control_dir()
        lock = None
        try:
            if fcntl is not None:
                if self.lock_path.is_symlink():
                    raise SourceCliStateError(
                        f"源码 CLI 锁文件是符号链接，拒绝使用: {self.lock_path}"
                    )
                lock = self.lock_path.open("a+", encoding="utf-8")
                if os.name != "nt":
                    os.chmod(self.lock_path, 0o600)
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if lock is not None:
                if fcntl is not None:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()

    def _ensure_control_dir(self) -> None:
        if self.control_dir.is_symlink():
            raise SourceCliStateError(
                f"源码 CLI 控制目录是符号链接，拒绝使用: {self.control_dir}"
            )
        try:
            self.control_dir.mkdir(mode=0o700, parents=False, exist_ok=True)
        except OSError as error:
            raise SourceCliStateError(
                f"无法创建源码 CLI 控制目录: {self.control_dir}: {error}"
            ) from error
        if not self.control_dir.is_dir():
            raise SourceCliStateError(f"源码 CLI 控制路径不是目录: {self.control_dir}")
        if os.name != "nt":
            os.chmod(self.control_dir, 0o700)

    @staticmethod
    def _safe_existing_file(path: Path) -> bool:
        if path.is_symlink():
            raise SourceCliStateError(f"源码 CLI 状态文件是符号链接，拒绝读取: {path}")
        return path.exists() and path.is_file()

    def _atomic_write_text(self, path: Path, content: str) -> None:
        if path.is_symlink():
            raise SourceCliStateError(f"源码 CLI 状态文件是符号链接，拒绝覆盖: {path}")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=str(self.control_dir)
        )
        temporary_path = Path(temporary_name)
        try:
            if os.name != "nt":
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(path)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise SourceCliStateError(
                f"无法写入源码 CLI 状态文件: {path}: {error}"
            ) from error


def _safe_history_command(command_line: str) -> bool:
    if not command_line.strip():
        return False
    try:
        arguments = shlex.split(command_line)
    except ValueError:
        return False
    if not arguments or arguments[0] in {"owner", "config"}:
        return False
    sensitive = {"--api-key", "--password", "--secret", "--token"}
    return not any(argument.split("=", 1)[0] in sensitive for argument in arguments)


__all__ = (
    "CANDIDATE_FILE_NAME",
    "CONTROL_DIR_NAME",
    "HISTORY_FILE_NAME",
    "SourceCliCandidate",
    "SourceCliState",
    "SourceCliStateError",
)
