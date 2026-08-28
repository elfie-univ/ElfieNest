from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from test.support.paths import PROJECT_ROOT

NODE_PROJECTS = (
    Path("app/interfaces/web/frontend"),
    Path("app/interfaces/desktop"),
    Path("docs"),
    Path("devtools/web"),
)
NODE_TOOLCHAIN_CHECK = PROJECT_ROOT / "scripts/quality/checks/node_toolchain.sh"


def _copy_node_project_manifests(source_root: Path, target_root: Path) -> None:
    (target_root / "package.json").write_text(
        (source_root / "package.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for project in NODE_PROJECTS:
        target_dir = target_root / project
        target_dir.mkdir(parents=True, exist_ok=True)
        source_dir = source_root / project
        shutil.copy2(source_dir / "package.json", target_dir / "package.json")
        shutil.copy2(source_dir / "pnpm-lock.yaml", target_dir / "pnpm-lock.yaml")


def test_node_toolchain_check_accepts_all_locked_projects() -> None:
    # Given: the repository's four independent Node projects and root toolchain anchor.
    result = subprocess.run(
        ["bash", str(NODE_TOOLCHAIN_CHECK)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: all package-manager and Node baseline declarations are consistent.
    assert result.returncode == 0, result.stderr
    assert "Node toolchain manifests are consistent" in result.stdout


def test_node_toolchain_check_rejects_a_project_with_a_different_pnpm(
    tmp_path: Path,
) -> None:
    # Given: a complete manifest set with one project changed to pnpm 11.
    _copy_node_project_manifests(PROJECT_ROOT, tmp_path)
    devtools_manifest = tmp_path / "devtools/web/package.json"
    manifest = json.loads(devtools_manifest.read_text(encoding="utf-8"))
    manifest["packageManager"] = "pnpm@11.5.2"
    devtools_manifest.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    # When: the read-only consistency check runs against that checkout.
    result = subprocess.run(
        ["bash", str(NODE_TOOLCHAIN_CHECK), str(tmp_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: it fails at the mismatched project and reports both versions.
    assert result.returncode == 1
    assert "devtools/web/package.json" in result.stderr
    assert "pnpm@11.5.2" in result.stderr
    assert "pnpm@10.12.1" in result.stderr
