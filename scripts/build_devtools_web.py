"""Build the shared Vite frontend for local Developer Tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

REPOSITORY_ROOT = Path(__file__).parents[1]
WEB_SOURCE = REPOSITORY_ROOT / "devtools" / "web"
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "build" / "components" / "devtools-web"
MANIFEST_NAME = "build-manifest.json"


def source_digest(source: Path) -> str:
    """Return a stable digest of source files that affect the Vite bundle."""
    digest = hashlib.sha256()
    for path in _source_files(source):
        digest.update(path.relative_to(source).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def bundle_is_current(output: Path, source: Path) -> bool:
    """Return whether an existing output directory matches the current source."""
    manifest_path = output / MANIFEST_NAME
    if not (output / "index.html").is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return manifest.get("source_digest") == source_digest(source)


def ensure_bundle(*, pnpm_command: str | None = None) -> Path:
    """Build only when the checked source differs from the staged Vite output."""
    if bundle_is_current(OUTPUT_DIRECTORY, WEB_SOURCE):
        return OUTPUT_DIRECTORY
    pnpm = pnpm_command or shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("未找到 pnpm，无法构建 Developer Tools 前端")
    install = [pnpm, "install", "--frozen-lockfile"]
    if not (WEB_SOURCE / "node_modules").is_dir():
        subprocess.run(install, cwd=WEB_SOURCE, check=True)
    subprocess.run([pnpm, "run", "build"], cwd=WEB_SOURCE, check=True)
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIRECTORY / MANIFEST_NAME).write_text(
        json.dumps({"source_digest": source_digest(WEB_SOURCE)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return OUTPUT_DIRECTORY


def _source_files(source: Path) -> Iterable[Path]:
    """Yield tracked frontend inputs while excluding local dependency caches."""
    for path in sorted(source.rglob("*")):
        if path.is_file() and "node_modules" not in path.parts:
            yield path


def main() -> int:
    """Provide an explicit and an automatic Developer Tools build command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensure", action="store_true")
    parser.parse_args()
    output = ensure_bundle()
    print(f"✅ Developer Tools Web 已是最新: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
