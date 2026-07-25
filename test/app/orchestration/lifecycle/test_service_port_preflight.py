from __future__ import annotations

from pathlib import Path

from app.orchestration.lifecycle.service import start_service
from app.orchestration.lifecycle.types import ServicePortsActiveError
from test.app.orchestration.lifecycle.service_fakes import (
    FailingInspector,
    RecordingLauncher,
)


def test_start_rejects_external_port_collision_before_launch(tmp_path: Path) -> None:
    # Given
    project_root = tmp_path / "project"
    elfie_home = tmp_path / "home"
    launcher = RecordingLauncher(5201)

    # When
    result = start_service(
        elfie_home,
        project_root,
        command=("python", "scripts/serve.py", "--port", "8000"),
        launcher=launcher,
        inspector=FailingInspector(),
        health_checker=lambda: False,
        service_ports_in_use=lambda ports: 8000 in ports,
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, ServicePortsActiveError)
    assert launcher.calls == []
