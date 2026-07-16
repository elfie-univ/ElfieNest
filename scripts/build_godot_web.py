#!/usr/bin/env python3
"""将 Godot 项目导出为 ElfieNest 内置的 Web Runtime。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GODOT_PROJECT = PROJECT_ROOT / "godot"
DEFAULT_OUTPUT = PROJECT_ROOT / "elfienest" / "ui" / "static" / "godot-web"
DESKTOP_OUTPUT = PROJECT_ROOT / "desktop" / "resources" / "godot-web"
PRESET_NAME = "Web"
ENTRY_NAME = "elfienest.html"
REQUIRED_SUFFIXES = (".html", ".js", ".wasm", ".pck")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建 ElfieNest Godot Web Runtime")
    parser.add_argument("--godot", type=Path, help="Godot 4 可执行文件")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="只检查现有产物")
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="允许 Godot 与项目版本不同（不建议用于发布）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    if args.check:
        return _print_bundle_check(output)

    binary = _find_godot(args.godot)
    if binary is None:
        print("❌ 未找到 Godot 4。请通过 --godot 或 GODOT_BIN 指定构建工具。")
        return 2
    required_version = _project_version()
    actual_version = _godot_version(binary)
    if (
        required_version
        and actual_version
        and required_version != actual_version
        and not args.allow_version_mismatch
    ):
        print(
            f"❌ 项目要求 Godot {required_version}，当前构建工具是 {actual_version}。"
        )
        print("   发布构建必须使用同版本 Godot 和同版本 Web Export Templates。")
        return 2

    staging = output.parent / f".{output.name}.staging"
    previous = output.parent / f".{output.name}.previous"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    entry = staging / ENTRY_NAME
    command = [
        str(binary),
        "--headless",
        "--path",
        str(GODOT_PROJECT),
        "--export-release",
        PRESET_NAME,
        str(entry),
    ]
    print(f"🔨 使用 Godot {actual_version or 'unknown'} 构建 Web Runtime...")
    result = subprocess.run(command, cwd=GODOT_PROJECT, check=False)
    if result.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        print("❌ Godot Web 导出失败。请确认已安装同版本 Web Export Templates。")
        _print_template_hint(required_version or actual_version or "对应")
        return result.returncode or 1

    missing = _missing_artifacts(staging)
    if missing:
        shutil.rmtree(staging, ignore_errors=True)
        print("❌ 导出命令完成，但产物不完整: " + ", ".join(missing))
        return 1

    _write_manifest(staging, actual_version or "unknown")
    shutil.rmtree(previous, ignore_errors=True)
    if output.exists():
        output.replace(previous)
    staging.replace(output)
    shutil.rmtree(previous, ignore_errors=True)
    if output == DEFAULT_OUTPUT:
        _sync_desktop_bundle(output)
    print(f"✅ Godot Web Runtime 已生成: {output}")
    print(f"   入口: {output / ENTRY_NAME}")
    return 0


def _print_bundle_check(output: Path) -> int:
    missing = _missing_artifacts(output)
    manifest = output / "build-manifest.json"
    if not manifest.is_file():
        missing.append("build-manifest.json")
    if missing:
        print(f"❌ Godot Web Runtime 不完整: {', '.join(missing)}")
        print("   运行: ./elfienest.sh build-godot-web")
        return 1
    print(f"✅ Godot Web Runtime 可用: {output / ENTRY_NAME}")
    return 0


def _missing_artifacts(directory: Path) -> List[str]:
    files = tuple(directory.glob("elfienest.*")) if directory.is_dir() else ()
    suffixes = {path.suffix for path in files if path.is_file()}
    return [suffix for suffix in REQUIRED_SUFFIXES if suffix not in suffixes]


def _write_manifest(directory: Path, godot_version: str) -> None:
    files: Dict[str, Dict[str, object]] = {}
    for path in sorted(item for item in directory.iterdir() if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[path.name] = {"bytes": path.stat().st_size, "sha256": digest}
    manifest = {
        "schema_version": 1,
        "godot_version": godot_version,
        "preset": PRESET_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry": ENTRY_NAME,
        "files": files,
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sync_desktop_bundle(output: Path) -> None:
    """同步正式 Web 产物到 Electron 发布资源目录。"""
    staging = DESKTOP_OUTPUT.parent / f".{DESKTOP_OUTPUT.name}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(output, staging)
    previous = DESKTOP_OUTPUT.with_name(f"{DESKTOP_OUTPUT.name}.previous")
    shutil.rmtree(previous, ignore_errors=True)
    if DESKTOP_OUTPUT.exists():
        DESKTOP_OUTPUT.replace(previous)
    staging.replace(DESKTOP_OUTPUT)
    shutil.rmtree(previous, ignore_errors=True)


def _find_godot(explicit: Optional[Path]) -> Optional[Path]:
    candidates: List[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    environment_binary = os.environ.get("GODOT_BIN", "").strip()
    if environment_binary:
        candidates.append(Path(environment_binary).expanduser())
    for name in ("godot4", "godot", "Godot", "godot4.exe", "godot.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    if platform.system() == "Darwin":
        candidates.extend(
            [
                Path("/Applications/Godot.app/Contents/MacOS/Godot"),
                Path.home() / "Applications/Godot.app/Contents/MacOS/Godot",
                Path.home() / "Downloads/Godot.app/Contents/MacOS/Godot",
            ]
        )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def _project_version() -> Optional[str]:
    text = (GODOT_PROJECT / "project.godot").read_text(encoding="utf-8")
    match = re.search(r'config/features=PackedStringArray\("(\d+\.\d+)"', text)
    return match.group(1) if match else None


def _godot_version(binary: Path) -> Optional[str]:
    result = subprocess.run(
        [str(binary), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    match = re.search(r"(\d+\.\d+)", result.stdout + result.stderr)
    return match.group(1) if match else None


def _print_template_hint(version: str) -> None:
    print(f"   在 Godot {version} 中打开：Editor > Manage Export Templates。")
    print("   安装官方 Export Templates 后重新运行构建命令。")


if __name__ == "__main__":
    raise SystemExit(main())
