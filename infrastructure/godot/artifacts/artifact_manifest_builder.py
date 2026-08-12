"""Artifact discovery and JSON writing for the runtime packaging handoff."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Mapping, Tuple

from infrastructure.godot.artifacts.artifact_manifest import (
    RuntimeArtifactComponent,
    RuntimeArtifactContractError,
    RuntimeArtifactFile,
    RuntimeArtifactManifest,
    RuntimeArtifactMode,
    RuntimeComponentKind,
    RuntimeTarget,
    RuntimeTargetRequirements,
    component_directory,
    expected_component_applicability,
    expected_required_components,
)


def build_runtime_artifact_manifest(
    component_root: Path, desktop_version: str
) -> RuntimeArtifactManifest:
    """Build the packaging handoff from already-exported runtime components."""
    components = (
        _build_godot_component(
            component_root,
            RuntimeComponentKind.GODOT_WEB,
            RuntimeArtifactMode.OBSERVER,
        ),
        _build_desktop_component(component_root, desktop_version),
        _build_godot_component(
            component_root,
            RuntimeComponentKind.LINUX_DEDICATED,
            RuntimeArtifactMode.DEDICATED_AUTHORITY,
        ),
    )
    targets = tuple(
        RuntimeTargetRequirements(target, expected_required_components(target))
        for target in RuntimeTarget
    )
    return RuntimeArtifactManifest(components=components, targets=targets)


def write_runtime_artifact_manifest(
    manifest: RuntimeArtifactManifest, output: Path
) -> None:
    """Write the reproducible JSON fixture consumed by package assembly."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_json_data(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_godot_component(
    component_root: Path,
    kind: RuntimeComponentKind,
    mode: RuntimeArtifactMode,
) -> RuntimeArtifactComponent:
    directory = component_root / component_directory(kind)
    metadata = _load_build_metadata(directory / "build-manifest.json")
    version = metadata.get("godot_version")
    entrypoint = metadata.get("entry")
    if not isinstance(version, str) or not version:
        raise RuntimeArtifactContractError(f"{kind.value}: godot_version is required")
    if not isinstance(entrypoint, str) or not entrypoint:
        raise RuntimeArtifactContractError(f"{kind.value}: entry is required")
    return RuntimeArtifactComponent(
        kind=kind,
        version=version,
        mode=mode,
        entrypoint=entrypoint,
        applicable_targets=expected_component_applicability(kind),
        files=_artifact_files(directory),
    )


def _build_desktop_component(
    component_root: Path, desktop_version: str
) -> RuntimeArtifactComponent:
    if not desktop_version:
        raise RuntimeArtifactContractError("desktop-observer: version is required")
    return RuntimeArtifactComponent(
        kind=RuntimeComponentKind.DESKTOP_OBSERVER,
        version=desktop_version,
        mode=RuntimeArtifactMode.OBSERVER,
        entrypoint="main.js",
        applicable_targets=expected_component_applicability(
            RuntimeComponentKind.DESKTOP_OBSERVER
        ),
        files=tuple(
            file
            for file in _artifact_files(
                component_root
                / component_directory(RuntimeComponentKind.DESKTOP_OBSERVER)
            )
            if not file.path.endswith(".test.js")
        ),
    )


def _artifact_files(directory: Path) -> Tuple[RuntimeArtifactFile, ...]:
    if not directory.is_dir():
        raise RuntimeArtifactContractError(
            f"component directory is missing: {directory}"
        )
    return tuple(
        RuntimeArtifactFile(
            path=path.relative_to(directory).as_posix(),
            bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            executable=bool(path.stat().st_mode & stat.S_IXUSR),
        )
        for path in sorted(item for item in directory.rglob("*") if item.is_file())
    )


def _load_build_metadata(path: Path) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeArtifactContractError(
            f"cannot read build metadata: {path}"
        ) from error
    if not isinstance(raw, dict):
        raise RuntimeArtifactContractError(f"build metadata must be an object: {path}")
    return raw
