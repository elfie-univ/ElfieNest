"""Exact-candidate pass cache for the tiered validation gate."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterator, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULE_VERSION = "tiered-validation-v1"


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


def candidate_fingerprint(base_sha: str, stage: str, paths: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(f"{RULE_VERSION}\0{stage}\0{base_sha}\0".encode())
    for path in paths:
        digest.update(path.encode("utf-8") + b"\0")
        candidate = PROJECT_ROOT / path
        digest.update(
            candidate.read_bytes() if candidate.is_file() else b"<deleted-or-non-file>"
        )
    for value in (
        sys.version,
        platform.platform(),
        platform.machine(),
        _tool_version(("uv", "--version")),
        _tool_version(("node", "--version")),
        _tool_version(("pnpm", "--version")),
    ):
        digest.update(value.encode("utf-8") + b"\0")
    return digest.hexdigest()


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


def cache_hit(cache_root: Path, key: str) -> bool:
    try:
        record = json.loads(_cache_file(cache_root, key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return record.get("key") == key and record.get("result") == "passed"


def cache_store(cache_root: Path, key: str, stage: str, base_sha: str) -> None:
    cache_root.mkdir(parents=True, exist_ok=True)
    record = {"key": key, "stage": stage, "base_sha": base_sha, "result": "passed"}
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=cache_root, delete=False
    ) as handle:
        json.dump(record, handle, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, _cache_file(cache_root, key))
