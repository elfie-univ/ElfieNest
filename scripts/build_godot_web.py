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
GODOT_PROJECT = PROJECT_ROOT / "godot_project"
DEFAULT_OUTPUT = PROJECT_ROOT / "build" / "components" / "godot-web"
PRESET_NAME = "Web"
ENTRY_NAME = "elfienest.html"
REQUIRED_SUFFIXES = (".html", ".js", ".wasm", ".pck")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建 ElfieNest Godot Web Runtime")
    parser.add_argument("--godot", type=Path, help="Godot 4 可执行文件")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="只检查现有产物")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="仅在 Web Runtime 缺失或 Godot 源码变化时重新导出",
    )
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
    if args.ensure and bundle_is_current(output, GODOT_PROJECT):
        print(f"✅ Godot Web Runtime 已是最新: {output / ENTRY_NAME}")
        return 0

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

    _write_manifest(staging, actual_version or "unknown", source_digest(GODOT_PROJECT))
    shutil.rmtree(previous, ignore_errors=True)
    if output.exists():
        output.replace(previous)
    staging.replace(output)
    shutil.rmtree(previous, ignore_errors=True)
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


def bundle_is_current(output: Path, project: Path) -> bool:
    """Whether an existing export exactly matches the tracked Godot sources."""
    if _missing_artifacts(output) or not (output / "build-manifest.json").is_file():
        return False
    try:
        manifest = json.loads((output / "build-manifest.json").read_text("utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(manifest, dict) and manifest.get(
        "source_digest"
    ) == source_digest(project)


def source_digest(project: Path) -> str:
    """Hash export-relevant project files while ignoring regenerable Godot metadata."""
    digest = hashlib.sha256()
    for path in sorted(project.rglob("*")):
        if not path.is_file() or _is_generated_godot_file(path, project):
            continue
        relative_path = path.relative_to(project).as_posix().encode("utf-8")
        digest.update(relative_path)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _is_generated_godot_file(path: Path, project: Path) -> bool:
    relative_path = path.relative_to(project)
    return (
        ".godot" in relative_path.parts
        or path.name.endswith(".import")
        or path.name.endswith(".uid")
    )


def _write_manifest(
    directory: Path, godot_version: str, source_digest_value: str
) -> None:
    files: Dict[str, Dict[str, object]] = {}
    for path in sorted(item for item in directory.iterdir() if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[path.name] = {"bytes": path.stat().st_size, "sha256": digest}
    manifest = {
        "schema_version": 1,
        "godot_version": godot_version,
        "preset": PRESET_NAME,
        "source_digest": source_digest_value,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry": ENTRY_NAME,
        "files": files,
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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
