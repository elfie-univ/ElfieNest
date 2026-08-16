"""JSON boundary parser for the typed runtime packaging handoff."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
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
)


def load_runtime_artifact_manifest(output: Path) -> RuntimeArtifactManifest:
    """Parse one untrusted JSON handoff into its typed runtime contract."""
    try:
        raw = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeArtifactContractError(f"cannot read contract: {error}") from error
    if not isinstance(raw, dict):
        raise RuntimeArtifactContractError("contract root must be an object")
    if raw.get("schema_version") != 1:
        raise RuntimeArtifactContractError("schema_version must be 1")
    return RuntimeArtifactManifest(
        components=_parse_components(raw.get("components")),
        targets=_parse_targets(raw.get("targets")),
    )


def _parse_components(raw: object) -> Tuple[RuntimeArtifactComponent, ...]:
    if not isinstance(raw, dict):
        raise RuntimeArtifactContractError("components must be an object")
    components = []
    for raw_kind, value in raw.items():
        if not isinstance(raw_kind, str) or not isinstance(value, dict):
            raise RuntimeArtifactContractError("component entry is invalid")
        components.append(_parse_component(raw_kind, value))
    return tuple(components)


def _parse_component(
    raw_kind: str, raw: Mapping[str, object]
) -> RuntimeArtifactComponent:
    try:
        kind = RuntimeComponentKind(raw_kind)
        mode = RuntimeArtifactMode(_required_string(raw, "mode"))
    except ValueError as error:
        raise RuntimeArtifactContractError(
            f"unknown component variant: {raw_kind}"
        ) from error
    applicability = _parse_targets_list(
        raw.get("applicable_targets"), "applicable_targets"
    )
    files = _parse_files(raw.get("files"))
    species_catalog_digest = raw.get("species_catalog_digest")
    if not isinstance(species_catalog_digest, str):
        raise RuntimeArtifactContractError("species_catalog_digest must be a string")
    return RuntimeArtifactComponent(
        kind=kind,
        version=_required_string(raw, "version"),
        mode=mode,
        entrypoint=_required_relative_path(raw, "entrypoint"),
        applicable_targets=frozenset(applicability),
        files=files,
        species_catalog_digest=species_catalog_digest,
    )


def _parse_targets(raw: object) -> Tuple[RuntimeTargetRequirements, ...]:
    if not isinstance(raw, dict):
        raise RuntimeArtifactContractError("targets must be an object")
    requirements = []
    for raw_target, value in raw.items():
        if not isinstance(raw_target, str) or not isinstance(value, dict):
            raise RuntimeArtifactContractError("target entry is invalid")
        try:
            target = RuntimeTarget(raw_target)
        except ValueError as error:
            raise RuntimeArtifactContractError(
                f"unknown target: {raw_target}"
            ) from error
        raw_components = value.get("required_components")
        if not isinstance(raw_components, list) or not all(
            isinstance(component, str) for component in raw_components
        ):
            raise RuntimeArtifactContractError(
                "required_components must be a string list"
            )
        try:
            components = frozenset(
                RuntimeComponentKind(component) for component in raw_components
            )
        except ValueError as error:
            raise RuntimeArtifactContractError("unknown required component") from error
        requirements.append(RuntimeTargetRequirements(target, components))
    return tuple(requirements)


def _parse_targets_list(raw: object, field: str) -> Tuple[RuntimeTarget, ...]:
    if not isinstance(raw, list) or not all(isinstance(target, str) for target in raw):
        raise RuntimeArtifactContractError(f"{field} must be a string list")
    try:
        return tuple(RuntimeTarget(target) for target in raw)
    except ValueError as error:
        raise RuntimeArtifactContractError(
            f"{field} contains an unknown target"
        ) from error


def _parse_files(raw: object) -> Tuple[RuntimeArtifactFile, ...]:
    if not isinstance(raw, list):
        raise RuntimeArtifactContractError("files must be a list")
    files = []
    for value in raw:
        if not isinstance(value, dict):
            raise RuntimeArtifactContractError("file entry must be an object")
        byte_count = value.get("bytes")
        checksum = value.get("sha256")
        executable = value.get("executable")
        if not isinstance(byte_count, int) or byte_count < 0:
            raise RuntimeArtifactContractError(
                "file bytes must be a non-negative integer"
            )
        if not isinstance(checksum, str) or not isinstance(executable, bool):
            raise RuntimeArtifactContractError(
                "file hash or executable flag is invalid"
            )
        files.append(
            RuntimeArtifactFile(
                path=_required_relative_path(value, "path"),
                bytes=byte_count,
                sha256=checksum,
                executable=executable,
            )
        )
    return tuple(files)


def _required_string(raw: Mapping[str, object], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeArtifactContractError(f"{field} must be a non-empty string")
    return value


def _required_relative_path(raw: Mapping[str, object], field: str) -> str:
    value = _required_string(raw, field)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeArtifactContractError(f"{field} must be a safe relative path")
    return value
