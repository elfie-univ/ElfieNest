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
)

LIFECYCLE = create_lifecycle_facade()


class _StoppedSupervisor:
    def status(self):
        return RuntimeSnapshotV1(
            instance_id="test",
            tier=BackendTier.OFFLINE,
            phase=RuntimePhase.OFFLINE,
            desired_target=RuntimeTarget.CORE,
            generation=0,
        ).projection()


def test_json_status_does_not_attach_by_port_to_an_existing_runtime(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    # Given: this installation has no lifecycle receipt, while another checkout
    # already serves an ElfieNest Core on the default port.
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

    # When: packaged Desktop asks its embedded CLI for current-project state.
    lifecycle_commands.show_service_status(LIFECYCLE, json_output=True)

    # Then: port evidence is not treated as an attachable Runtime authority.
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "offline"
    assert payload["tier"] == "offline"
    assert payload["generation"] == 0
    assert payload["owner_lease"] is None


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
