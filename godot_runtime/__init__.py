"""Godot Runtime host selection, launch, and artifact metadata boundary."""

from godot_runtime.artifact_metadata import RuntimeArtifactMetadata, artifact_metadata
from godot_runtime.host_contract import (
    RuntimeDisplayMode,
    RuntimeHostDescriptor,
    RuntimeHostKind,
    RuntimeHostSelectionContext,
    select_authority_host,
    select_platform_authority_host,
)
from godot_runtime.launcher import (
    AuthorityLaunchError,
    AuthorityLaunchFailureKind,
    AuthorityLaunchPlan,
    AuthorityLaunchRequest,
    find_runtime_binary,
    start_godot_runtime,
    stop_godot_runtime,
)

__all__ = (
    "AuthorityLaunchError",
    "AuthorityLaunchFailureKind",
    "AuthorityLaunchPlan",
    "AuthorityLaunchRequest",
    "RuntimeArtifactMetadata",
    "RuntimeDisplayMode",
    "RuntimeHostDescriptor",
    "RuntimeHostKind",
    "RuntimeHostSelectionContext",
    "artifact_metadata",
    "find_runtime_binary",
    "select_authority_host",
    "select_platform_authority_host",
    "start_godot_runtime",
    "stop_godot_runtime",
)
