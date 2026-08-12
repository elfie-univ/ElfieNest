"""Focused tests for the Godot authority-host lifecycle adapter."""

import inspect
from pathlib import Path

import pytest

from app.orchestration.lifecycle.ports import AuthorityHostConfig
from app.orchestration.lifecycle.types import AuthorityHostError
from infrastructure.godot.lifecycle import authority
from infrastructure.godot.lifecycle.launcher import (
    AuthorityLaunchError,
    AuthorityLaunchFailureKind,
)


class _UnusedInspector:
    def exists(self, pid: int) -> bool:
        return False

    def cwd(self, pid: int) -> Path:
        raise AssertionError(pid)

    def command(self, pid: int) -> tuple[str, ...]:
        raise AssertionError(pid)


def test_authority_adapter_translates_launch_error(monkeypatch, tmp_path: Path) -> None:
    adapter = authority.GodotAuthorityHostAdapter(
        AuthorityHostConfig(
            project_root=tmp_path,
            http_port=8000,
            ws_port=8765,
            nonce="generation",
        ),
        inspector=_UnusedInspector(),
    )

    def fail(_request):
        raise AuthorityLaunchError(
            AuthorityLaunchFailureKind.MISSING_ARTIFACT, "missing host"
        )

    monkeypatch.setattr(authority, "start_godot_runtime", fail)

    with pytest.raises(AuthorityHostError, match="missing host"):
        adapter.start()


def test_authority_adapter_does_not_signal_unmatched_receipt(
    monkeypatch, tmp_path: Path
) -> None:
    class Inspector:
        def exists(self, pid: int) -> bool:
            return True

        def cwd(self, pid: int) -> Path:
            return tmp_path / "another-checkout"

        def command(self, pid: int) -> tuple[str, ...]:
            return ("unknown",)

    adapter = authority.GodotAuthorityHostAdapter(
        AuthorityHostConfig(
            project_root=tmp_path,
            http_port=8000,
            ws_port=8765,
            nonce="generation",
        ),
        inspector=Inspector(),
    )
    signals = []
    monkeypatch.setattr(
        authority.os, "killpg", lambda pid, sig: signals.append((pid, sig))
    )

    class Recovered:
        pid = 55

    adapter.stop(Recovered())

    assert signals == []


def test_godot_authority_requires_bootstrap_to_inject_process_inspection() -> None:
    source = inspect.getsource(authority)

    assert "infrastructure.platform" not in source
    assert "DefaultProcessInspector" not in source
