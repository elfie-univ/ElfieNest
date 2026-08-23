#!/usr/bin/env python3
"""Assemble one checksum-verified desktop resource tree for Electron."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infrastructure.persistence.configuration.species import load_species_catalog
from scripts.internal.build import package_python_core
from scripts.internal.release import version as check_release_version

PROJECT_ROOT: Final = Path(__file__).resolve().parents[3]
DEFAULT_STAGING_ROOT: Final = PROJECT_ROOT / "build" / "staging"
DEFAULT_WEB_SOURCE: Final = PROJECT_ROOT / "build" / "web"
DEFAULT_GODOT_SOURCE: Final = PROJECT_ROOT / "build" / "components" / "godot-web"
DEFAULT_CONFIG_SOURCE: Final = PROJECT_ROOT / "config"
REQUIRED_WEB_FILES: Final = ("manifest.json", "index.html")
REQUIRED_GODOT_FILES: Final = (
    "elfienest.html",
    "elfienest.js",
    "elfienest.wasm",
    "elfienest.pck",
)


class ResourceAssemblyError(RuntimeError):
    """Raised when a release resource cannot enter target staging."""


def _source_revision(project_root: Path = PROJECT_ROOT) -> str:
    try:
        revision = subprocess.check_output(
            ("git", "rev-parse", "HEAD"),
            cwd=project_root,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ResourceAssemblyError("resource-source-revision-unavailable") from error
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ResourceAssemblyError("resource-source-revision-invalid")
    return revision


def _target_executable(target: str, stem: str) -> str:
    return f"{stem}.exe" if target == "win32-x64" else stem


def _require_files(directory: Path, names: Iterable[str], component: str) -> None:
    missing = [name for name in names if not (directory / name).is_file()]
    if missing:
        raise ResourceAssemblyError(
            f"resource-component-incomplete component={component} missing={','.join(missing)}"
        )


def _copy_directory(source: Path, destination: Path, component: str) -> None:
    if not source.is_dir():
        raise ResourceAssemblyError(
            f"resource-component-missing component={component} path={source}"
        )
    shutil.copytree(source, destination)


def _manifest_files(root: Path) -> Mapping[str, Mapping[str, object]]:
    files: dict[str, Mapping[str, object]] = {}
    for path in sorted(
        candidate for candidate in root.rglob("*") if candidate.is_file()
    ):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        files[relative] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return files


def _write_manifest(
    resources: Path,
    application_version: str,
    source_revision: str,
    target: str,
) -> None:
    manifest = {
        "schema_version": 2,
        "application_version": application_version,
        "source_revision": source_revision,
        "target": target,
        "files": _manifest_files(resources),
    }
    (resources / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def assemble_resources(
    target: str,
    output_root: Path,
    web_source: Path,
    godot_source: Path,
    core_source: Path,
    cli_source: Path,
    application_version: str,
    source_revision: str,
    config_source: Path | None = None,
) -> Path:
    """Build one atomic flat resource root from validated component inputs."""
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise ResourceAssemblyError("resource-source-revision-invalid")
    if target not in package_python_core.TARGETS:
        raise ResourceAssemblyError(f"resource-target-unsupported target={target}")
    _require_files(web_source, REQUIRED_WEB_FILES, "web")
    _require_files(godot_source, REQUIRED_GODOT_FILES, "godot-web")
    core_name = _target_executable(target, "ElfieNestCore")
    if not core_source.is_file() or core_source.name != core_name:
        raise ResourceAssemblyError(
            f"resource-component-missing component=python-core path={core_source}"
        )
    cli_name = _target_executable(target, "ElfieNestCli")
    if not cli_source.is_file() or cli_source.name != cli_name:
        raise ResourceAssemblyError(
            f"resource-component-missing component=management-cli path={cli_source}"
        )
    selected_config_source = config_source or DEFAULT_CONFIG_SOURCE
    if not selected_config_source.is_dir():
        raise ResourceAssemblyError(
            f"resource-component-missing component=config path={selected_config_source}"
        )
    try:
        load_species_catalog(root=selected_config_source)
    except (OSError, ValueError, RuntimeError) as error:
        raise ResourceAssemblyError(
            f"resource-component-incomplete component=species-config path={selected_config_source}"
        ) from error
    target_root = output_root / target
    resources = target_root / "resources"
    staging = output_root / f".{target}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        _copy_directory(web_source, staging / "resources" / "web", "web")
        _copy_directory(godot_source, staging / "resources" / "godot-web", "godot-web")
        _copy_directory(
            selected_config_source,
            staging / "resources" / "config",
            "config",
        )
        core_destination = staging / "resources" / "python-core"
        core_destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(core_source, core_destination / core_name)
        cli_destination = staging / "resources" / "management-cli"
        cli_destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cli_source, cli_destination / cli_name)
        _write_manifest(
            staging / "resources", application_version, source_revision, target
        )
        shutil.rmtree(target_root, ignore_errors=True)
        staging.replace(target_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return resources


def parse_args() -> argparse.Namespace:
    """Parse the one-target staging command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=package_python_core.TARGETS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_STAGING_ROOT)
    parser.add_argument("--web-source", type=Path, default=DEFAULT_WEB_SOURCE)
    parser.add_argument("--godot-source", type=Path, default=DEFAULT_GODOT_SOURCE)
    parser.add_argument("--config-source", type=Path, default=DEFAULT_CONFIG_SOURCE)
    parser.add_argument("--core-source", type=Path)
    parser.add_argument("--cli-source", type=Path)
    return parser.parse_args()


def main() -> int:
    """Assemble portable application resources for one native target."""
    args = parse_args()
    target = str(args.target)
    try:
        core_source = args.core_source or (
            PROJECT_ROOT
            / "build"
            / "python-core"
            / target
            / _target_executable(target, "ElfieNestCore")
        )
        cli_source = args.cli_source or (
            PROJECT_ROOT
            / "build"
            / "python-cli"
            / target
            / _target_executable(target, "ElfieNestCli")
        )
        resources = assemble_resources(
            target=target,
            output_root=args.output_root,
            web_source=args.web_source,
            godot_source=args.godot_source,
            core_source=core_source,
            cli_source=cli_source,
            config_source=args.config_source,
            application_version=check_release_version.project_version(),
            source_revision=_source_revision(),
        )
    except (
        ResourceAssemblyError,
        check_release_version.ReleaseVersionError,
        OSError,
    ) as error:
        print(str(error))
        return 1
    print(f"desktop-resources-assembled target={target} resources={resources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
