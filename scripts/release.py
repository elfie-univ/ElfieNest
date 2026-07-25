#!/usr/bin/env python3
"""ElfieNest 发布构建脚本 - 组装 staging 资源并调用 electron-builder。

用法:
    python scripts/release.py --target darwin-arm64
    python scripts/release.py --target win32-x64
    python scripts/release.py --target linux-x64

流程:
    1. 调用 bootstrap.sh ensure --tier=prod
    2. 构建 Godot web（如果环境允许）
    3. 组装 build/staging/<target>/resources/
    4. 运行 build-resource-manifest
    5. 调用 electron-builder
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DESKTOP_DIR = PROJECT_ROOT / "desktop"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"

SUPPORTED_TARGETS = ["darwin-arm64", "darwin-x64", "win32-x64", "linux-x64"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ElfieNest 发布构建脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=SUPPORTED_TARGETS,
        help="目标平台和架构",
    )
    parser.add_argument(
        "--skip-godot",
        action="store_true",
        help="跳过 Godot web 构建（假设产物已存在）",
    )
    parser.add_argument(
        "--skip-package",
        action="store_true",
        help="只组装 staging，不调用 electron-builder",
    )
    return parser.parse_args()


def run_command(cmd: List[str], cwd: Optional[Path] = None) -> int:
    """运行命令并实时输出。"""
    print(f"  🔧 执行: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def ensure_dependencies() -> bool:
    """确保所有依赖已就绪。"""
    print("\n📦 检查依赖...")
    bootstrap = SCRIPTS_DIR / "bootstrap.sh"

    result = run_command([str(bootstrap), "ensure", "--tier=prod"])
    if result != 0:
        print("❌ 依赖检查失败")
        return False

    return True


def build_godot_web() -> bool:
    """构建 Godot web 产物。"""
    print("\n📦 构建 Godot Web Runtime...")

    godot_web_dir = BUILD_DIR / "components" / "godot-web"
    required_files = [
        godot_web_dir / "elfienest.html",
        godot_web_dir / "elfienest.js",
        godot_web_dir / "elfienest.wasm",
        godot_web_dir / "elfienest.pck",
    ]

    # 检查是否已存在
    if all(f.exists() for f in required_files):
        print("  ✅ Godot Web Runtime 已存在")
        return True

    # 尝试构建
    build_script = SCRIPTS_DIR / "build_godot_web.py"
    result = run_command(
        [sys.executable, str(build_script), "--ensure"],
        cwd=PROJECT_ROOT,
    )

    if result != 0:
        print("  ⚠️  Godot web 构建失败（需要本机安装 Godot 4.7 编辑器）")
        print("  💡 请手动安装 Godot 并运行: ./elfienest.sh build-godot-web")
        return False

    return True


def assemble_staging(target: str) -> bool:
    """组装 staging 目录。"""
    print(f"\n📦 组装 staging 资源 ({target})...")

    staging_dir = BUILD_DIR / "staging" / target / "resources"

    # 清理旧目录
    if staging_dir.exists():
        print(f"  🗑️  清理旧目录: {staging_dir}")
        shutil.rmtree(staging_dir)

    staging_dir.mkdir(parents=True, exist_ok=True)

    # 1. 复制前端产物
    print("  📋 复制前端产物...")
    web_src = BUILD_DIR / "web"
    web_dst = staging_dir / "web"

    if not web_src.exists():
        print(f"  ❌ 前端产物不存在: {web_src}")
        return False

    shutil.copytree(web_src, web_dst)
    print(f"  ✅ 前端产物已复制到: {web_dst}")

    # 2. 复制 Godot web 产物
    print("  📋 复制 Godot Web Runtime...")
    godot_src = BUILD_DIR / "components" / "godot-web"
    godot_dst = staging_dir / "godot-web"

    if not godot_src.exists():
        print(f"  ⚠️  Godot web 产物不存在，跳过")
    else:
        shutil.copytree(godot_src, godot_dst)
        print(f"  ✅ Godot web 已复制到: {godot_dst}")

    # 3. 提示 Python Core 和 Ollama（需要单独准备）
    print("\n  ⚠️  注意：以下资源需要单独准备：")
    print(f"     - {staging_dir / 'python-core' / 'ElfieNestCore'}")
    print(f"     - {staging_dir / 'ollama' / 'ollama'}")
    print("  💡 请参考 desktop/packaging/runtime-resources.md")

    return True


def build_resource_manifest(target: str) -> bool:
    """生成资源清单。"""
    print(f"\n📦 生成资源清单 ({target})...")

    build_manifest_script = DESKTOP_DIR / "src" / "resources" / "build_resource_manifest.js"
    staging_resources = BUILD_DIR / "staging" / target / "resources"
    manifest_output = staging_resources / "manifest.json"

    if not build_manifest_script.exists():
        print(f"  ❌ build_resource_manifest.js 不存在")
        print("  💡 请先构建 desktop: cd desktop && pnpm build")
        return False

    # 检查 desktop 是否已构建
    desktop_build = BUILD_DIR / "components" / "desktop"
    if not desktop_build.exists():
        print("  🔧 正在构建 desktop...")
        result = run_command(
            ["pnpm", "build"],
            cwd=DESKTOP_DIR,
        )
        if result != 0:
            print("  ❌ desktop 构建失败")
            return False

    result = run_command(
        ["node", str(build_manifest_script), str(staging_resources), str(manifest_output), target],
        cwd=PROJECT_ROOT,
    )

    if result != 0:
        print("  ❌ 资源清单生成失败")
        return False

    print(f"  ✅ 资源清单已生成: {manifest_output}")
    return True


def run_electron_builder(target: str) -> bool:
    """调用 electron-builder 打包。"""
    print(f"\n📦 调用 electron-builder ({target})...")

    # 设置环境变量
    env = os.environ.copy()
    env["ELFIENEST_TARGET"] = target

    result = run_command(
        ["pnpm", "package"],
        cwd=DESKTOP_DIR,
    )

    if result != 0:
        print("  ❌ electron-builder 打包失败")
        return False

    print(f"  ✅ 安装包已生成到: {DIST_DIR}")
    return True


def main() -> int:
    args = parse_args()

    print("=" * 60)
    print("🦊 ElfieNest 发布构建")
    print("=" * 60)
    print(f"目标平台: {args.target}")
    print(f"跳过 Godot: {args.skip_godot}")
    print(f"跳过打包: {args.skip_package}")
    print("=" * 60)

    # 1. 确保依赖
    if not ensure_dependencies():
        return 1

    # 2. 构建 Godot web
    if not args.skip_godot:
        if not build_godot_web():
            print("\n⚠️  Godot web 构建失败，但继续组装其他资源...")

    # 3. 组装 staging
    if not assemble_staging(args.target):
        return 1

    # 4. 生成资源清单
    if not build_resource_manifest(args.target):
        print("\n⚠️  资源清单生成失败，跳过...")

    # 5. 调用 electron-builder
    if not args.skip_package:
        if not run_electron_builder(args.target):
            return 1

    print("\n" + "=" * 60)
    print("✅ 发布构建完成！")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
