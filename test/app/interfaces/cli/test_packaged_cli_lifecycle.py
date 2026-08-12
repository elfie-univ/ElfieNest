"""Contracts for the frozen management CLI's checkout-independent Core command."""

from __future__ import annotations

import pytest

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade


def test_lifecycle_commands_use_the_packaged_core_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a frozen management CLI identifies its sibling packaged Core.
    core = "/Applications/ElfieNest.app/Contents/Resources/python-core/ElfieNestCore"
    monkeypatch.setenv("ELFIENEST_CORE_BIN", core)

    # When: it forms a background service command.
    command = create_lifecycle_facade().default_service_command(("--lan",))

    # Then: no source checkout script is referenced.
    assert command == (core, "--lan")
