"""Typed runtime artifact handoff model for native package assembly."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Dict, Set, Tuple


class RuntimeArtifactContractError(ValueError):
    """Raised when a serialized runtime artifact contract cannot be parsed."""


class RuntimeTarget(str, Enum):
    """Closed native package target matrix."""

    DARWIN_ARM64 = "darwin-arm64"
    DARWIN_X64 = "darwin-x64"
    WIN32_X64 = "win32-x64"
    LINUX_X64 = "linux-x64"


class RuntimeComponentKind(str, Enum):
    """Runtime components supplied to the package assembly owner."""

    GODOT_WEB = "godot-web"
    DESKTOP_OBSERVER = "desktop-observer"
    LINUX_DEDICATED = "linux-dedicated"


class RuntimeArtifactMode(str, Enum):
    """The runtime role reached through a component entrypoint."""

    OBSERVER = "observer"
    DEDICATED_AUTHORITY = "dedicated-authority"


@dataclass(frozen=True)
class RuntimeArtifactFile:
    """One content-addressed relative component file."""

    path: str
    bytes: int
    sha256: str
    executable: bool


@dataclass(frozen=True)
class RuntimeArtifactComponent:
    """A versioned, mode-specific component available to package assembly."""

    kind: RuntimeComponentKind
    version: str
    mode: RuntimeArtifactMode
    entrypoint: str
    applicable_targets: frozenset[RuntimeTarget]
    files: Tuple[RuntimeArtifactFile, ...]


@dataclass(frozen=True)
class RuntimeTargetRequirements:
    """The exact runtime components a native target must package."""

    target: RuntimeTarget
    required_components: frozenset[RuntimeComponentKind]


@dataclass(frozen=True)
class RuntimeArtifactManifest:
    """The sole typed source for the runtime-to-packaging handoff payload."""

    components: Tuple[RuntimeArtifactComponent, ...]
    targets: Tuple[RuntimeTargetRequirements, ...]

    def component(self, kind: RuntimeComponentKind) -> RuntimeArtifactComponent:
        """Return one uniquely named component."""
        for component in self.components:
            if component.kind is kind:
                return component
        raise RuntimeArtifactContractError(f"missing component {kind.value}")

    def required_components_for(
        self, target: RuntimeTarget
    ) -> frozenset[RuntimeComponentKind]:
        """Return the exact component set requested by one packaging target."""
        for requirement in self.targets:
            if requirement.target is target:
                return requirement.required_components
        raise RuntimeArtifactContractError(f"missing target {target.value}")

    def with_component(
        self, replacement: RuntimeArtifactComponent
    ) -> RuntimeArtifactManifest:
        """Return a fixture variant with exactly one component replaced."""
        components = tuple(
            replacement if component.kind is replacement.kind else component
            for component in self.components
        )
        return replace(self, components=components)

    def with_required_components(
        self,
        target: RuntimeTarget,
        components: Set[RuntimeComponentKind],
    ) -> RuntimeArtifactManifest:
        """Return a fixture variant with a replacement target requirement."""
        requirements = tuple(
            RuntimeTargetRequirements(target, frozenset(components))
            if requirement.target is target
            else requirement
            for requirement in self.targets
        )
        return replace(self, targets=requirements)

    def to_json_data(self) -> Dict[str, object]:
        """Serialize the typed contract without a parallel hand-written schema."""
        return {
            "schema_version": 1,
            "components": {
                component.kind.value: {
                    "version": component.version,
                    "mode": component.mode.value,
                    "entrypoint": component.entrypoint,
                    "applicable_targets": sorted(
                        target.value for target in component.applicable_targets
                    ),
                    "files": [
                        {
                            "path": file.path,
                            "bytes": file.bytes,
                            "sha256": file.sha256,
                            "executable": file.executable,
                        }
                        for file in component.files
                    ],
                }
                for component in self.components
            },
            "targets": {
                requirement.target.value: {
                    "required_components": sorted(
                        component.value for component in requirement.required_components
                    )
                }
                for requirement in self.targets
            },
        }


_ALL_TARGETS = frozenset(RuntimeTarget)
_COMPONENT_DIRECTORIES = {
    RuntimeComponentKind.GODOT_WEB: "godot-web",
    RuntimeComponentKind.DESKTOP_OBSERVER: "desktop-interface",
    RuntimeComponentKind.LINUX_DEDICATED: "godot-linux-dedicated",
}
_EXPECTED_APPLICABILITY = {
    RuntimeComponentKind.GODOT_WEB: _ALL_TARGETS,
    RuntimeComponentKind.DESKTOP_OBSERVER: _ALL_TARGETS,
    RuntimeComponentKind.LINUX_DEDICATED: frozenset({RuntimeTarget.LINUX_X64}),
}
_EXPECTED_MODES = {
    RuntimeComponentKind.GODOT_WEB: RuntimeArtifactMode.OBSERVER,
    RuntimeComponentKind.DESKTOP_OBSERVER: RuntimeArtifactMode.OBSERVER,
    RuntimeComponentKind.LINUX_DEDICATED: RuntimeArtifactMode.DEDICATED_AUTHORITY,
}
_EXPECTED_REQUIRED_COMPONENTS = {
    RuntimeTarget.DARWIN_ARM64: frozenset(
        {RuntimeComponentKind.GODOT_WEB, RuntimeComponentKind.DESKTOP_OBSERVER}
    ),
    RuntimeTarget.DARWIN_X64: frozenset(
        {RuntimeComponentKind.GODOT_WEB, RuntimeComponentKind.DESKTOP_OBSERVER}
    ),
    RuntimeTarget.WIN32_X64: frozenset(
        {RuntimeComponentKind.GODOT_WEB, RuntimeComponentKind.DESKTOP_OBSERVER}
    ),
    RuntimeTarget.LINUX_X64: frozenset(
        {
            RuntimeComponentKind.GODOT_WEB,
            RuntimeComponentKind.DESKTOP_OBSERVER,
            RuntimeComponentKind.LINUX_DEDICATED,
        }
    ),
}


def component_directory(kind: RuntimeComponentKind) -> str:
    """Return the fixed build component directory for one component kind."""
    return _COMPONENT_DIRECTORIES[kind]


def expected_component_applicability(
    kind: RuntimeComponentKind,
) -> frozenset[RuntimeTarget]:
    """Return the only valid target applicability set for one component."""
    return _EXPECTED_APPLICABILITY[kind]


def expected_component_mode(kind: RuntimeComponentKind) -> RuntimeArtifactMode:
    """Return the only valid runtime mode for one component kind."""
    return _EXPECTED_MODES[kind]


def expected_required_components(
    target: RuntimeTarget,
) -> frozenset[RuntimeComponentKind]:
    """Return the only valid required set for one native target."""
    return _EXPECTED_REQUIRED_COMPONENTS[target]


def write_runtime_artifact_manifest(
    manifest: RuntimeArtifactManifest, output: Path
) -> None:
    """Write the reproducible JSON fixture consumed by package assembly."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_json_data(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_runtime_artifact_manifest(
    component_root: Path, desktop_version: str
) -> RuntimeArtifactManifest:
    """Build the packaging handoff from already-exported runtime components."""
    from godot_runtime.artifact_manifest_builder import build_runtime_artifact_manifest

    return build_runtime_artifact_manifest(component_root, desktop_version)


def load_runtime_artifact_manifest(output: Path) -> RuntimeArtifactManifest:
    """Parse one untrusted JSON handoff into its typed runtime contract."""
    from godot_runtime.artifact_manifest_parser import load_runtime_artifact_manifest

    return load_runtime_artifact_manifest(output)


def validate_runtime_artifact_manifest(
    manifest: RuntimeArtifactManifest, component_root: Path
) -> Tuple[str, ...]:
    """Validate a handoff without coupling this model to filesystem checks."""
    from godot_runtime.artifact_validator import validate_runtime_artifact_manifest

    return validate_runtime_artifact_manifest(manifest, component_root)
