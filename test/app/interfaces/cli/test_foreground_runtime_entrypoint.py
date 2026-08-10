from __future__ import annotations

import os
from argparse import Namespace

import pytest

from app.bootstrap.lifecycle import create_lifecycle_facade
from app.interfaces.cli import foreground_runtime, lifecycle_commands
from app.orchestration.lifecycle.runtime_health import RuntimeHealth
from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    ServiceLifecycleResult,
)
from scripts import elfienest


class AlreadyRunningSupervisor:
    """Minimal non-owning Supervisor for packaged command adaptation."""

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        return ServiceLifecycleResult(status="already_running")

    def status(self) -> RuntimeHealth:
        raise AssertionError("non-owner must not inspect foreground health")

    def stop(self) -> ServiceLifecycleResult:
        raise AssertionError("non-owner must not stop the Runtime")


class ExecMustNotRun(Exception):
    """Prove the foreground CLI never replaces itself with Core."""


def test_packaged_core_uses_supervisor_without_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    core = "/Applications/ElfieNest.app/Contents/Resources/ElfieNestCore"
    monkeypatch.setenv("ELFIENEST_CORE_BIN", core)
    supervisor = AlreadyRunningSupervisor()
    factory_calls: list[tuple[tuple[str, ...], int]] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda _lifecycle, command, port: (
            factory_calls.append((tuple(command), port)) or supervisor
        ),
    )
    monkeypatch.setattr(
        os, "execvp", lambda *_args: (_ for _ in ()).throw(ExecMustNotRun)
    )

    # When
    result = foreground_runtime.run_foreground_service(
        create_lifecycle_facade(), ("--port", "8123")
    )

    # Then
    assert result.status == "already_running"
    assert factory_calls == [((core, "--port", "8123"), 8123)]


def test_serve_start_failure_maps_to_exit_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    failure = ServiceLifecycleResult(
        status="failed", error=LaunchFailedError("startup failed")
    )
    monkeypatch.setattr(
        elfienest,
        "run_foreground_service",
        lambda _lifecycle, _options: failure,
        raising=False,
    )
    monkeypatch.setattr(
        elfienest.os,
        "execvp",
        lambda *_args: (_ for _ in ()).throw(ExecMustNotRun),
    )
    args = Namespace(
        command="serve",
        force=False,
        port=None,
        ws_port=None,
        godot_ws_port=None,
        fallback=False,
        no_seed_elfie=False,
    )

    # When / Then
    with pytest.raises(SystemExit) as error:
        elfienest._dispatch_command(args, create_lifecycle_facade())
    assert error.value.code == 1
