"""Godot Web Runtime 产物检查。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GODOT_WEB_DIR = PROJECT_ROOT / "build" / "components" / "godot-web"
GODOT_WEB_ENTRY = GODOT_WEB_DIR / "elfienest.html"
GODOT_WEB_MANIFEST = GODOT_WEB_DIR / "build-manifest.json"
REQUIRED_SUFFIXES = (".html", ".js", ".wasm", ".pck")


@dataclass(frozen=True)
class GodotWebBundleStatus:
    ready: bool
    entry_url: str
    directory: Path
    missing: Tuple[str, ...]
    manifest: Dict[str, object]
    integrity_errors: Tuple[str, ...]


def inspect_godot_web_bundle(
    directory: Path = GODOT_WEB_DIR,
) -> GodotWebBundleStatus:
    files = tuple(path for path in directory.glob("elfienest.*") if path.is_file())
    suffixes = {path.suffix for path in files}
    missing = tuple(suffix for suffix in REQUIRED_SUFFIXES if suffix not in suffixes)
    manifest_path = directory / GODOT_WEB_MANIFEST.name
    manifest: Dict[str, object] = {}
    integrity_errors: list[str] = []
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            manifest = payload
    if not manifest_path.is_file():
        missing += (GODOT_WEB_MANIFEST.name,)
    else:
        raw_files = manifest.get("files")
        if not isinstance(raw_files, dict):
            integrity_errors.append("manifest.files 缺失或格式无效")
        else:
            for filename, expected in raw_files.items():
                if not isinstance(filename, str) or not _is_safe_manifest_filename(filename):
                    integrity_errors.append(f"manifest 文件名无效: {filename}")
                    continue
                path = directory / filename
                if not path.is_file():
                    integrity_errors.append(f"manifest 文件缺失: {filename}")
                    continue
                if not isinstance(expected, dict):
                    integrity_errors.append(f"manifest 条目无效: {filename}")
                    continue
                expected_bytes = expected.get("bytes")
                expected_sha256 = expected.get("sha256")
                if not isinstance(expected_bytes, int) or not isinstance(expected_sha256, str):
                    integrity_errors.append(f"manifest 校验字段缺失: {filename}")
                    continue
                actual_bytes = path.stat().st_size
                actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_bytes != expected_bytes:
                    integrity_errors.append(
                        f"manifest bytes 不匹配: {filename} ({actual_bytes} != {expected_bytes})"
                    )
                if actual_sha256 != expected_sha256:
                    integrity_errors.append(f"manifest sha256 不匹配: {filename}")
            for suffix in REQUIRED_SUFFIXES:
                filename = f"elfienest{suffix}"
                if filename not in raw_files:
                    integrity_errors.append(f"manifest 未声明文件: {filename}")
    return GodotWebBundleStatus(
        ready=not missing and not integrity_errors,
        entry_url="/runtime/godot/elfienest.html",
        directory=directory,
        missing=missing,
        manifest=manifest,
        integrity_errors=tuple(integrity_errors),
    )


def _is_safe_manifest_filename(filename: str) -> bool:
    """仅允许 manifest 声明当前 bundle 目录内的普通文件名。"""
    path = Path(filename)
    return path.name == filename and not path.is_absolute() and filename != ""
