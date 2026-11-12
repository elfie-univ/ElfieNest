"""Prepare and publish the two Nest Lab previews as one validated bundle."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from infrastructure.godot.artifacts.web_build import (
    DEFAULT_OUTPUT,
    _build_lock,
    current_source_fingerprint,
    runtime_is_current,
)

ROOT = Path(__file__).resolve().parents[2]
PUBLISHER = ROOT / "godot_project/tools/publish_static_asset_review.py"


def _assets_current(output: Path) -> bool:
    return (
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(PUBLISHER),
                "--check-nest-assets",
                "--web-output",
                str(output),
            ],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )


def ensure_preview_bundle(output: Path = DEFAULT_OUTPUT) -> None:
    """Keep the previous pair live until both replacement previews are ready."""
    with _build_lock(output):
        fingerprint = current_source_fingerprint()
        runtime_current = runtime_is_current(output)
        if runtime_current and _assets_current(output):
            return
        staging = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.preview-", dir=output.parent)
        )
        previous = output.parent / f".{output.name}.preview-previous"
        try:
            if runtime_current:
                shutil.copytree(output, staging, dirs_exist_ok=True)
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/internal/build/build_godot_web.py"),
                    "--ensure",
                    "--output",
                    str(staging),
                ],
                cwd=ROOT,
                check=True,
            )
            if not _assets_current(staging):
                subprocess.run(
                    [
                        "bash",
                        "scripts/quality/checks/godot_host.sh",
                        "res://tools/pack_nest_assets.gd",
                    ],
                    cwd=ROOT,
                    check=True,
                )
                subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(PUBLISHER),
                        "--nest-assets",
                        "--web-output",
                        str(staging),
                    ],
                    cwd=ROOT,
                    check=True,
                )
            if (
                fingerprint != current_source_fingerprint()
                or not runtime_is_current(staging)
                or not _assets_current(staging)
            ):
                raise RuntimeError(
                    "Nest preview sources changed during build; refresh to retry"
                )
            shutil.rmtree(previous, ignore_errors=True)
            if output.exists():
                output.replace(previous)
            try:
                staging.replace(output)
            except OSError:
                if previous.exists():
                    previous.replace(output)
                raise
            shutil.rmtree(previous, ignore_errors=True)
        finally:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    ensure_preview_bundle()
