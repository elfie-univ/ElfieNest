"""Focused tests for the Godot authority-host lifecycle adapter."""

import inspect
import json
import signal
from pathlib import Path
from types import SimpleNamespace

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


def test_authority_adapter_reads_current_core_pid_before_launch(
    monkeypatch, tmp_path: Path
) -> None:
    core_pid_file = tmp_path / "elfienest.pid"
    core_pid_file.write_text("7315", encoding="utf-8")
    adapter = authority.GodotAuthorityHostAdapter(
        AuthorityHostConfig(
            project_root=tmp_path,
            http_port=8000,
            ws_port=8765,
            nonce="generation",
            core_pid_file=core_pid_file,
        ),
        inspector=_UnusedInspector(),
    )
    captured = []

    class Process:
        pid = 7316

    def start(request):
        captured.append(request)
        return Process()

    monkeypatch.setattr(authority, "start_godot_runtime", start)

    assert adapter.start().pid == 7316
    assert captured[0].core_pid == 7315


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


def test_recorded_authority_stop_persists_requested_and_terminal_events(
    monkeypatch, tmp_path: Path
) -> None:
    class Inspector:
        alive = True

        def exists(self, _pid: int) -> bool:
            return self.alive

        def cwd(self, _pid: int) -> Path:
            return tmp_path

        def command(self, _pid: int) -> tuple[str, ...]:
            return ("electron", authority.AUTHORITY_ROLE_ARGUMENT)

    inspector = Inspector()
    adapter = authority.GodotAuthorityHostAdapter(
        AuthorityHostConfig(
            project_root=tmp_path,
            http_port=8000,
            ws_port=8765,
            nonce="generation",
            core_pid_file=tmp_path / "elfienest.pid",
        ),
        inspector=inspector,
    )
    monkeypatch.setattr(
        authority,
        "plan_godot_runtime_launch",
        lambda _request: SimpleNamespace(
            host_kind=authority.RuntimeHostKind.ELECTRON_AUTHORITY,
            command=("electron", authority.AUTHORITY_ROLE_ARGUMENT),
        ),
    )
    monkeypatch.setattr(authority.os, "getpgid", lambda pid: pid)

    def terminate_group(pid: int, sent_signal: int) -> None:
        assert (pid, sent_signal) == (55, signal.SIGTERM)
        inspector.alive = False

    monkeypatch.setattr(authority.os, "killpg", terminate_group)

    class Recovered:
        pid = 55

    adapter.stop(Recovered())

    events = [
        json.loads(line)
        for line in (tmp_path / "logs/authority.log")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event"] for event in events] == [
        "authority_shutdown_requested",
        "authority_process_stopped",
    ]
    assert all(event["pid"] == 55 for event in events)
    assert events[0]["signal"] == "SIGTERM"
    assert events[1]["status"] == "stopped"
    assert all(event["observer_role"] == "lifecycle-supervisor" for event in events)


def test_recorded_authority_timeout_logs_escalation_without_false_stop(
    monkeypatch, tmp_path: Path
) -> None:
    class Inspector:
        def exists(self, _pid: int) -> bool:
            return True

        def cwd(self, _pid: int) -> Path:
            return tmp_path

        def command(self, _pid: int) -> tuple[str, ...]:
            return ("electron", authority.AUTHORITY_ROLE_ARGUMENT)

    adapter = authority.GodotAuthorityHostAdapter(
        AuthorityHostConfig(
            project_root=tmp_path,
            http_port=8000,
            ws_port=8765,
            nonce="generation",
            core_pid_file=tmp_path / "elfienest.pid",
        ),
        inspector=Inspector(),
        stop_timeout_seconds=0.0,
    )
    monkeypatch.setattr(
        authority,
        "plan_godot_runtime_launch",
        lambda _request: SimpleNamespace(
            host_kind=authority.RuntimeHostKind.ELECTRON_AUTHORITY,
            command=("electron", authority.AUTHORITY_ROLE_ARGUMENT),
        ),
    )
    monkeypatch.setattr(authority.os, "getpgid", lambda pid: pid)
    forced_signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        authority.os,
        "killpg",
        lambda pid, sent_signal: forced_signals.append((pid, sent_signal)),
    )

    class Recovered:
        pid = 56

    adapter.stop(Recovered())

    events = [
        json.loads(line)
        for line in (tmp_path / "logs/authority.log")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event"] for event in events] == [
        "authority_shutdown_requested",
        "authority_shutdown_escalated",
    ]
    assert events[1]["status"] == "forced"
    assert events[1]["signal"] == "SIGKILL"
    assert forced_signals == [
        (56, signal.SIGTERM),
        (56, signal.SIGKILL),
    ]


def test_owned_authority_stop_does_not_report_stopped_while_process_is_alive(
    monkeypatch, tmp_path: Path
) -> None:
    class OwnedProcess:
        pid = 57
        returncode = None

        def poll(self) -> None:
            return None

    adapter = authority.GodotAuthorityHostAdapter(
        AuthorityHostConfig(
            project_root=tmp_path,
            http_port=8000,
            ws_port=8765,
            nonce="generation",
            core_pid_file=tmp_path / "elfienest.pid",
        ),
        inspector=_UnusedInspector(),
    )
    monkeypatch.setattr(authority, "Popen", OwnedProcess)
    monkeypatch.setattr(authority, "stop_godot_runtime", lambda _process: None)

    adapter.stop(OwnedProcess())

    events = [
        json.loads(line)
        for line in (tmp_path / "logs/authority.log")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event"] for event in events] == [
        "authority_shutdown_requested",
        "authority_process_stop_failed",
    ]
    assert events[1]["status"] == "still_running"
    assert "exit_code" not in events[1]


def test_godot_authority_requires_bootstrap_to_inject_process_inspection() -> None:
    source = inspect.getsource(authority)

    assert "infrastructure.platform" not in source
    assert "DefaultProcessInspector" not in source
