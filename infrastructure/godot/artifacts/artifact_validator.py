"""Validation for the typed runtime artifact packaging handoff."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import AbstractSet, List, Tuple

from infrastructure.godot.artifacts.artifact_manifest import (
    RuntimeArtifactComponent,
    RuntimeArtifactManifest,
    RuntimeComponentKind,
    RuntimeTarget,
    component_directory,
    expected_component_applicability,
    expected_component_mode,
    expected_required_components,
)


def validate_runtime_artifact_manifest(
    manifest: RuntimeArtifactManifest, component_root: Path
) -> Tuple[str, ...]:
    """Return deterministic errors for an invalid handoff or component payload."""
    errors = _manifest_shape_errors(manifest)
    for component in manifest.components:
        errors.extend(_component_payload_errors(component, component_root))
    return tuple(errors)


def _manifest_shape_errors(manifest: RuntimeArtifactManifest) -> List[str]:
    errors: List[str] = []
    component_kinds = [component.kind for component in manifest.components]
    if len(component_kinds) != len(set(component_kinds)):
        errors.append("component kinds must be unique")
    if set(component_kinds) != set(RuntimeComponentKind):
        errors.append("component kinds must match the runtime contract")
    target_values = [requirement.target for requirement in manifest.targets]
    if len(target_values) != len(set(target_values)):
        errors.append("target requirements must be unique")
    if set(target_values) != set(RuntimeTarget):
        errors.append("target requirements must cover the full target matrix")
    for component in manifest.components:
        expected_mode = expected_component_mode(component.kind)
        if component.mode is not expected_mode:
            errors.append(f"{component.kind.value}: mode must be {expected_mode.value}")
        expected_applicability = expected_component_applicability(component.kind)
        if component.applicable_targets != expected_applicability:
            errors.append(
                "{}: applicability must be {}".format(
                    component.kind.value,
                    ",".join(sorted(target.value for target in expected_applicability)),
                )
            )
        errors.extend(_component_contract_errors(component))
    for target in RuntimeTarget:
        try:
            observed = manifest.required_components_for(target)
        except ValueError:
            continue
        expected_components = expected_required_components(target)
        errors.extend(_target_requirement_errors(target, observed, expected_components))
    return errors


def _component_contract_errors(component: RuntimeArtifactComponent) -> List[str]:
    errors: List[str] = []
    paths = [file.path for file in component.files]
    if len(paths) != len(set(paths)):
        errors.append(f"{component.kind.value}: file paths must be unique")
    if component.entrypoint not in paths:
        errors.append(
            f"{component.kind.value}: mode entry {component.entrypoint} is not declared"
        )
    for file in component.files:
        if (
            component.kind is RuntimeComponentKind.DESKTOP_OBSERVER
            and file.path.endswith(".test.js")
        ):
            errors.append(f"desktop-observer: {file.path} must not be packaged")
        if not _is_sha256(file.sha256):
            errors.append(f"{component.kind.value}: {file.path} has invalid sha256")
    if component.kind is RuntimeComponentKind.DESKTOP_OBSERVER:
        if component.species_catalog_digest:
            errors.append("desktop-observer: species_catalog_digest must be empty")
    elif not _is_sha256(component.species_catalog_digest):
        errors.append(
            f"{component.kind.value}: species_catalog_digest has invalid sha256"
        )
    return errors


def _target_requirement_errors(
    target: RuntimeTarget,
    observed: AbstractSet[RuntimeComponentKind],
    expected: AbstractSet[RuntimeComponentKind],
) -> List[str]:
    errors: List[str] = []
    for component in sorted(expected - observed, key=lambda item: item.value):
        errors.append(f"{target.value}: missing required component {component.value}")
    for component in sorted(observed - expected, key=lambda item: item.value):
        if component is RuntimeComponentKind.LINUX_DEDICATED:
            errors.append(f"{target.value}: linux-dedicated must not be required")
        else:
            errors.append(f"{target.value}: {component.value} must not be required")
    return errors


def _component_payload_errors(
    component: RuntimeArtifactComponent, component_root: Path
) -> List[str]:
    errors: List[str] = []
    directory = component_root / component_directory(component.kind)
    if not directory.is_dir():
        return [f"{component.kind.value}: component directory is missing"]
    declared_paths = {file.path for file in component.files}
    actual_paths = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
        and not (
            component.kind is RuntimeComponentKind.DESKTOP_OBSERVER
            and path.name.endswith(".test.js")
        )
    }
    for missing in sorted(declared_paths - actual_paths):
        errors.append(f"{component.kind.value}: {missing} is missing")
    for unexpected in sorted(actual_paths - declared_paths):
        errors.append(f"{component.kind.value}: {unexpected} is undeclared")
    for file in component.files:
        path = directory / file.path
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if len(payload) != file.bytes:
            errors.append(f"{component.kind.value}: {file.path} byte count mismatch")
        if hashlib.sha256(payload).hexdigest() != file.sha256:
            errors.append(f"{component.kind.value}: {file.path} sha256 mismatch")
        executable = bool(path.stat().st_mode & stat.S_IXUSR)
        if executable is not file.executable:
            errors.append(
                f"{component.kind.value}: {file.path} executable bit mismatch"
            )
    return errors


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
