"""Candidate and expensive-backstop pass caches for tiered validation."""

from __future__ import annotations

import contextlib
import functools
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Mapping, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULE_VERSION = "tiered-validation-v4"
CACHE_ENVIRONMENT_KEYS = (
    "CI",
    "ELFIENEST_HOME",
    "GITHUB_ACTIONS",
    "GODOT_BIN",
    "HOME",
    "OLLAMA_HOST",
    "PATH",
    "PYTHONHASHSEED",
    "PYTHONPATH",
)


@dataclass(frozen=True)
class RepositorySnapshot:
    """One content snapshot shared by all checks in one local invocation."""

    paths: Tuple[str, ...]
    signatures: Mapping[str, str]
    values: Mapping[str, str]
    runtime_values: Tuple[str, ...]

    def value_for(self, path: str) -> Optional[str]:
        return self.values.get(path)


def _path_signature(path: str) -> str:
    candidate = PROJECT_ROOT / path
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return "<deleted-or-non-file>"
    parts = [
        f"mode:{metadata.st_mode & 0o7777:o}",
        f"size:{metadata.st_size}",
        f"mtime:{getattr(metadata, 'st_mtime_ns', int(metadata.st_mtime * 1_000_000_000))}",
    ]
    if candidate.is_symlink():
        parts.append(f"symlink:{os.readlink(candidate)}")
    return "\0".join(parts)


def _path_value(path: str) -> str:
    candidate = PROJECT_ROOT / path
    digest = hashlib.sha256()
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        digest.update(b"<deleted-or-non-file>")
        return digest.hexdigest()
    digest.update(f"mode:{metadata.st_mode & 0o7777:o}\0".encode())
    if candidate.is_symlink():
        digest.update(f"symlink:{os.readlink(candidate)}".encode())
    elif candidate.is_file():
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    else:
        digest.update(b"<non-file>")
    return digest.hexdigest()


@functools.cache
def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return f"{package}:missing"


def installed_package_version(package: str) -> str:
    return _package_version(package)


def _stable_environment_value(key: str) -> str:
    value = os.environ.get(key, "<unset>")
    if key != "PATH":
        return value
    transient_markers = ("/.codex/tmp/arg0/", "\\.codex\\tmp\\arg0\\")
    return os.pathsep.join(
        entry
        for entry in value.split(os.pathsep)
        if not any(marker in entry for marker in transient_markers)
    )


def _runtime_fingerprint_values() -> Tuple[str, ...]:
    values = [
        sys.version,
        platform.platform(),
        platform.machine(),
        _tool_version(("uv", "--version")),
        _tool_version(("node", "--version")),
        _tool_version(("pnpm", "--version")),
        f"pytest:{_package_version('pytest')}",
        f"pytest-cov:{_package_version('pytest-cov')}",
        f"coverage:{_package_version('coverage')}",
    ]
    values.extend(
        f"env:{key}={_stable_environment_value(key)}" for key in CACHE_ENVIRONMENT_KEYS
    )
    return tuple(values)


def repository_snapshot(paths: Sequence[str]) -> RepositorySnapshot:
    normalized = tuple(sorted(set(paths)))
    return RepositorySnapshot(
        paths=normalized,
        signatures={path: _path_signature(path) for path in normalized},
        values={path: _path_value(path) for path in normalized},
        runtime_values=_runtime_fingerprint_values(),
    )


def repository_snapshot_current(
    snapshot: RepositorySnapshot, paths: Sequence[str]
) -> bool:
    normalized = tuple(sorted(set(paths)))
    if normalized != snapshot.paths:
        return False
    if _runtime_fingerprint_values() != snapshot.runtime_values:
        return False
    return all(
        _path_signature(path) == snapshot.signatures[path] for path in normalized
    )


@functools.cache
def _tool_version(command: Sequence[str]) -> str:
    executable = shutil.which(command[0])
    if not executable:
        return f"{command[0]}:missing"
    result = subprocess.run(
        [executable, *command[1:]],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return (result.stdout or result.stderr).strip() or f"{command[0]}:unknown"


def scoped_fingerprint(
    namespace: str,
    paths: Sequence[str],
    command: Sequence[str] = (),
    *,
    snapshot: Optional[RepositorySnapshot] = None,
) -> str:
    """Hash current contents and tools for one reusable deterministic check."""

    digest = hashlib.sha256()
    digest.update(f"{RULE_VERSION}\0{namespace}\0".encode())
    for argument in command:
        digest.update(argument.encode("utf-8") + b"\0")
    for path in sorted(set(paths)):
        digest.update(path.encode("utf-8") + b"\0")
        value = snapshot.value_for(path) if snapshot is not None else None
        digest.update((value or _path_value(path)).encode("utf-8") + b"\0")
    for value in (
        snapshot.runtime_values
        if snapshot is not None
        else _runtime_fingerprint_values()
    ):
        digest.update(value.encode("utf-8") + b"\0")
    return digest.hexdigest()


def candidate_fingerprint(
    base_sha: str,
    stage: str,
    paths: Sequence[str],
    *,
    snapshot: Optional[RepositorySnapshot] = None,
) -> str:
    return scoped_fingerprint(f"candidate:{stage}:{base_sha}", paths, snapshot=snapshot)


def check_fingerprint(
    base_sha: str,
    check_id: str,
    paths: Sequence[str],
    command: Sequence[str],
    *,
    snapshot: Optional[RepositorySnapshot] = None,
) -> str:
    """Fingerprint one check independently from the delivery stage."""

    return scoped_fingerprint(
        f"candidate-check:{check_id}:{base_sha}",
        paths,
        command,
        snapshot=snapshot,
    )


def _is_task_closure_metadata(path: str) -> bool:
    """Return whether a root path is a task acceptance matrix, not test input."""

    return (
        "/" not in path and path.startswith("task-closure") and path.endswith(".json")
    )


def backstop_fingerprint(base_sha: str, paths: Sequence[str]) -> str:
    """Fingerprint inputs that can change the expensive G3 backstop result.

    Task-closure matrices are deliberately omitted because they are checked
    again for every exact candidate. Every other changed path is fail-closed
    and remains part of the backstop input.
    """

    backstop_paths = [path for path in paths if not _is_task_closure_metadata(path)]
    return candidate_fingerprint(base_sha, "main-backstop", backstop_paths)


@contextlib.contextmanager
def cache_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        yield
    finally:
        handle.close()


def _cache_file(cache_root: Path, key: str) -> Path:
    return cache_root / f"{key}.json"


def cache_record(cache_root: Path, key: str) -> Optional[Dict[str, object]]:
    try:
        record = json.loads(_cache_file(cache_root, key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def cache_hit(cache_root: Path, key: str) -> bool:
    record = cache_record(cache_root, key)
    return bool(
        record and record.get("key") == key and record.get("result") == "passed"
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_invalidate(cache_root: Path, key: str) -> None:
    """Remove a stale pass record after the same deterministic input fails."""

    _cache_file(cache_root, key).unlink(missing_ok=True)


def cache_store(
    cache_root: Path,
    key: str,
    stage: str,
    base_sha: str,
    *,
    reused_from: Optional[str] = None,
    metadata: Optional[Mapping[str, object]] = None,
) -> None:
    cache_root.mkdir(parents=True, exist_ok=True)
    record: Dict[str, object] = {
        "key": key,
        "stage": stage,
        "base_sha": base_sha,
        "result": "passed",
    }
    if reused_from is not None:
        record["reused_from"] = reused_from
    if metadata is not None:
        record["metadata"] = dict(metadata)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=cache_root, delete=False
    ) as handle:
        json.dump(record, handle, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, _cache_file(cache_root, key))
