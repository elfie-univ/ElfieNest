#!/usr/bin/env python3
"""Assemble one checksum-verified desktop resource tree for Electron."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Final, Iterable, Mapping, Sequence

from scripts import check_release_version, package_python_core

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_STAGING_ROOT: Final = PROJECT_ROOT / "build" / "staging"
DEFAULT_WEB_SOURCE: Final = PROJECT_ROOT / "build" / "web"
DEFAULT_GODOT_SOURCE: Final = PROJECT_ROOT / "build" / "components" / "godot-web"
REQUIRED_WEB_FILES: Final = ("manifest.json", "login.html", "chat.html", "manage.html")
REQUIRED_GODOT_FILES: Final = (
    "elfienest.html",
    "elfienest.js",
    "elfienest.wasm",
    "elfienest.pck",
)


class ResourceAssemblyError(RuntimeError):
    """Raised when a release resource cannot enter target staging."""


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


def _safe_members(archive: tarfile.TarFile) -> Sequence[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        if member.islnk() or member.issym() or Path(member.name).is_absolute() or ".." in Path(member.name).parts:
            raise ResourceAssemblyError(f"ollama-archive-unsafe-member path={member.name}")
    return members


def _extract_ollama_archive(archive: Path, destination: Path, executable: str) -> None:
    with tempfile.TemporaryDirectory(prefix="elfienest-ollama-") as temporary:
        extracted = Path(temporary)
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    if Path(member.filename).is_absolute() or ".." in Path(member.filename).parts:
                        raise ResourceAssemblyError(
                            f"ollama-archive-unsafe-member path={member.filename}"
                        )
                bundle.extractall(extracted)
        elif archive.name.endswith((".tgz", ".tar.gz")):
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted, members=_safe_members(bundle))
        elif archive.name.endswith(".tar.zst"):
            _extract_zstd_tar(archive, extracted)
        else:
            raise ResourceAssemblyError(
                f"ollama-archive-format-unsupported path={archive.name}"
            )
        candidates = sorted(path for path in extracted.rglob(executable) if path.is_file())
        if len(candidates) != 1:
            raise ResourceAssemblyError(
                f"ollama-archive-executable-invalid executable={executable} count={len(candidates)}"
            )
        source_executable = candidates[0]
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_executable, destination / executable)
        source_root = source_executable.parent.parent
        for child in source_root.iterdir():
            if child == source_executable.parent:
                for nested in child.iterdir():
                    if nested == source_executable:
                        continue
                    _copy_path(nested, destination / nested.name)
                continue
            _copy_path(child, destination / child.name)


def _extract_zstd_tar(archive: Path, destination: Path) -> None:
    try:
        import zstandard
    except ImportError as error:
        raise ResourceAssemblyError("ollama-zstd-dependency-missing") from error
    with archive.open("rb") as source:
        with zstandard.ZstdDecompressor().stream_reader(source) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as bundle:
                for member in bundle:
                    if (
                        member.islnk()
                        or member.issym()
                        or Path(member.name).is_absolute()
                        or ".." in Path(member.name).parts
                    ):
                        raise ResourceAssemblyError(
                            f"ollama-archive-unsafe-member path={member.name}"
                        )
                    bundle.extract(member, destination)


def _copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def _manifest_files(root: Path) -> Mapping[str, Mapping[str, object]]:
    files: dict[str, Mapping[str, object]] = {}
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "manifest.json":
            continue
        data = path.read_bytes()
        files[relative] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return files


def _write_manifest(resources: Path, application_version: str, target: str) -> None:
    manifest = {
        "schema_version": 1,
        "application_version": application_version,
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
    ollama_archive: Path,
    ollama_source: package_python_core.OllamaSource,
    application_version: str,
) -> Path:
    """Build one atomic flat resource root from validated component inputs."""
    if target not in package_python_core.TARGETS:
        raise ResourceAssemblyError(f"resource-target-unsupported target={target}")
    if ollama_source.target != target:
        raise ResourceAssemblyError(
            f"ollama-source-target-mismatch target={target} source_target={ollama_source.target}"
        )
    package_python_core.verify_ollama_source(ollama_archive, ollama_source)
    _require_files(web_source, REQUIRED_WEB_FILES, "web")
    _require_files(godot_source, REQUIRED_GODOT_FILES, "godot-web")
    core_name = _target_executable(target, "ElfieNestCore")
    if not core_source.is_file() or core_source.name != core_name:
        raise ResourceAssemblyError(
            f"resource-component-missing component=python-core path={core_source}"
        )
    target_root = output_root / target
    resources = target_root / "resources"
    staging = output_root / f".{target}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        _copy_directory(web_source, staging / "resources" / "web", "web")
        _copy_directory(godot_source, staging / "resources" / "godot-web", "godot-web")
        core_destination = staging / "resources" / "python-core"
        core_destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(core_source, core_destination / core_name)
        _extract_ollama_archive(
            ollama_archive,
            staging / "resources" / "ollama",
            _target_executable(target, "ollama"),
        )
        _write_manifest(staging / "resources", application_version, target)
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
    parser.add_argument("--core-source", type=Path)
    parser.add_argument("--ollama-archive", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Assemble a staging tree after resolving its immutable sidecar source."""
    args = parse_args()
    target = str(args.target)
    try:
        source = package_python_core.load_ollama_sources().for_target(target)
        core_source = args.core_source or (
            PROJECT_ROOT
            / "build"
            / "python-core"
            / target
            / _target_executable(target, "ElfieNestCore")
        )
        resources = assemble_resources(
            target=target,
            output_root=args.output_root,
            web_source=args.web_source,
            godot_source=args.godot_source,
            core_source=core_source,
            ollama_archive=args.ollama_archive,
            ollama_source=source,
            application_version=check_release_version.project_version(),
        )
    except (
        ResourceAssemblyError,
        package_python_core.OllamaSourceError,
        check_release_version.ReleaseVersionError,
        OSError,
    ) as error:
        print(str(error))
        return 1
    print(f"desktop-resources-assembled target={target} resources={resources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
