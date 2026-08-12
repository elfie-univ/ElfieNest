"""Artifact identities consumed by Godot Runtime hosts."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.godot.lifecycle.host_contract import (
    RuntimeHostDescriptor,
    RuntimeHostKind,
)


@dataclass(frozen=True)
class RuntimeArtifactMetadata:
    """Names the exported artifact a selected host is allowed to consume."""

    component: str
    entrypoint: str


def artifact_metadata(host: RuntimeHostDescriptor) -> RuntimeArtifactMetadata:
    """Return host artifact metadata without inspecting or building Godot source."""
    artifacts = {
        RuntimeHostKind.WEB_AUTHORITY: RuntimeArtifactMetadata(
            "godot-web", "elfienest.html"
        ),
        RuntimeHostKind.ELECTRON_AUTHORITY: RuntimeArtifactMetadata(
            "godot-web", "elfienest.html"
        ),
        RuntimeHostKind.LINUX_DEDICATED: RuntimeArtifactMetadata(
            "godot-linux-dedicated", "ElfieNestRuntime"
        ),
    }
    return artifacts[host.kind]
