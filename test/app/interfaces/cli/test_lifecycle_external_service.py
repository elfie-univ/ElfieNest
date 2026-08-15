from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle import (
    BackendTier,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
    ServicePortStatus,
)
from app.orchestration.lifecycle.ports import ProcessSnapshot

LIFECYCLE = create_lifecycle_facade()
PID_FILENAME = "elfienest.pid"


class _StoppedSupervisor:
    def status(self):
        return RuntimeSnapshotV1(
            instance_id="test",
            tier=BackendTier.OFFLINE,
            phase=RuntimePhase.OFFLINE,
            desired_target=RuntimeTarget.CORE,
            generation=0,
        ).projection()


def test_status_marks_default_ports_as_external_when_pid_belongs_elsewhere(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    # Given: the shared production PID receipt points at another checkout.
    elfie_home = tmp_path / "home"
    elfie_home.mkdir()
    (elfie_home / PID_FILENAME).write_text("15727", encoding="utf-8")
    external_root = tmp_path / "other-checkout"
    external_root.mkdir()
    monkeypatch.setattr(
        LIFECYCLE,
        "select_data_home",
        lambda *_args, **_kwargs: elfie_home,
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(LIFECYCLE, "recorded_pid", lambda *_args: 15727)
    monkeypatch.setattr(LIFECYCLE, "process_exists", lambda pid: pid == 15727)
    monkeypatch.setattr(
        LIFECYCLE,
        "inspect_process",
        lambda pid: ProcessSnapshot(
            pid=pid,
            cwd=external_root,
            command=("python", "scripts/serve.py"),
        ),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "default_port_statuses",
        lambda: [ServicePortStatus(port=8000, name="HTTP", running=True)],
    )

    # When: the user asks for status from the current worktree.
    lifecycle_commands.show_service_status(LIFECYCLE)

    # Then: a live external service is not reported as the current project.
    output = capsys.readouterr().out
    assert "another ElfieNest checkout" in output
    assert "occupied by external process" in output
    assert "✅ HTTP" not in output


def test_web_opens_healthy_default_service_without_starting_another_one(
    monkeypatch,
) -> None:
    # Given: no current-project PID receipt is verified, but the default Web is healthy.
    opened: list[str] = []
    start_calls: list[str] = []
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000: port == 8000,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda _lifecycle: start_calls.append("start"),
    )

    # When: the user runs `web`.
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then: the existing healthy page opens and no duplicate service is launched.
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8000/"]
    assert start_calls == []


def test_web_reports_external_port_owner_when_default_health_fails(
    monkeypatch,
    capsys,
) -> None:
    # Given: another process occupies the default Web port but is not healthy.
    opened: list[str] = []
    start_calls: list[str] = []
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000: False,
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "default_port_statuses",
        lambda: [ServicePortStatus(port=8000, name="HTTP", running=True)],
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda _lifecycle: start_calls.append("start"),
    )

    # When: the user runs `web`.
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then: the CLI reports the external owner class instead of starting again.
    assert result.status == "failed"
    assert opened == []
    assert start_calls == []
    assert "occupied by external process" in capsys.readouterr().out


def test_json_status_attaches_to_an_existing_elfienest_runtime(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    # Given: this installation has no lifecycle receipt, while another checkout
    # already serves an authenticated ElfieNest Core on the default port.
    monkeypatch.setattr(
        LIFECYCLE,
        "select_data_home",
        lambda *_args, **_kwargs: tmp_path / "home",
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: _StoppedSupervisor(),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=200,
            body=json.dumps(
                {
                    "status": "ok",
                    "engine_ready": True,
                    "godot_web_ready": True,
                    "godot_runtime_ready": False,
                }
            ).encode("utf-8"),
        ),
    )
    monkeypatch.setattr(LIFECYCLE, "optional_component_ready", lambda: False)

    # When: packaged Desktop asks its embedded CLI for attachable Runtime state.
    lifecycle_commands.show_service_status(LIFECYCLE, json_output=True)

    # Then: it sees an attached degraded Runtime and does not try to start a
    # second Core. The missing owner lease also prevents Desktop from stopping it.
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "core_ready"
    assert payload["tier"] == "core_ready"
    assert payload["generation"] == 0
    assert payload["owner_lease"] is None
    assert {item["name"]: item["state"] for item in payload["components"]} == {
        "core": "ready",
        "gateway": "ready",
        "godot_authority": "failed",
        "ollama": "degraded",
    }


def test_json_status_rejects_an_unrelated_http_service(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    # Given: an unrelated HTTP server happens to answer successfully on port 8000.
    monkeypatch.setattr(
        LIFECYCLE,
        "select_data_home",
        lambda *_args, **_kwargs: tmp_path / "home",
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: _StoppedSupervisor(),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=200,
            body=b'{"status":"ok"}',
        ),
    )
    monkeypatch.setattr(LIFECYCLE, "optional_component_ready", lambda: False)

    # When: packaged Desktop asks for lifecycle status.
    lifecycle_commands.show_service_status(LIFECYCLE, json_output=True)

    # Then: the unrelated endpoint is not treated as an attachable ElfieNest Runtime.
    payload = json.loads(capsys.readouterr().out)
    assert payload["components"] == []
    assert payload["generation"] == 0
    assert payload["owner_lease"] is None
    assert payload["state"] == "offline"
    assert payload["tier"] == "offline"
