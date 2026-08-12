"""Godot runtime artifact metadata and package handoff contracts."""

from infrastructure.godot.artifacts.artifact_manifest import (
    RuntimeArtifactComponent,
    RuntimeArtifactContractError,
    RuntimeArtifactFile,
    RuntimeArtifactManifest,
    RuntimeArtifactMode,
    RuntimeComponentKind,
    RuntimeTarget,
    RuntimeTargetRequirements,
    build_runtime_artifact_manifest,
    load_runtime_artifact_manifest,
    validate_runtime_artifact_manifest,
    write_runtime_artifact_manifest,
)
from infrastructure.godot.artifacts.artifact_metadata import (
    RuntimeArtifactMetadata,
    artifact_metadata,
)

__all__ = (
    "RuntimeArtifactComponent",
    "RuntimeArtifactContractError",
    "RuntimeArtifactFile",
    "RuntimeArtifactManifest",
    "RuntimeArtifactMetadata",
    "RuntimeArtifactMode",
    "RuntimeComponentKind",
    "RuntimeTarget",
    "RuntimeTargetRequirements",
    "artifact_metadata",
    "build_runtime_artifact_manifest",
    "load_runtime_artifact_manifest",
    "validate_runtime_artifact_manifest",
    "write_runtime_artifact_manifest",
)
