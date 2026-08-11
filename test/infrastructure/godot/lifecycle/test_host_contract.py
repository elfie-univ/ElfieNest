"""Tests for the importable Godot Runtime host boundary."""

from __future__ import annotations

from infrastructure.godot.artifacts import artifact_metadata
from infrastructure.godot.lifecycle import (
    RuntimeDisplayMode,
    RuntimeHostKind,
    select_authority_host,
)


def test_linux_dedicated_host_selects_displayless_runtime_artifact() -> None:
    # Given: Linux Dedicated is requested as an authority host.
    requested_kind = RuntimeHostKind.LINUX_DEDICATED

    # When: the host selection boundary resolves its descriptor and artifact.
    host = select_authority_host(requested_kind)
    artifact = artifact_metadata(host)

    # Then: it selects no-display hosting and the dedicated export identity.
    assert host.display_mode is RuntimeDisplayMode.DISPLAYLESS
    assert artifact.component == "godot-linux-dedicated"
    assert artifact.entrypoint == "ElfieNestRuntime"
