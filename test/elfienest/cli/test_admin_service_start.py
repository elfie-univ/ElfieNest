from __future__ import annotations

from pathlib import Path
from typing import Callable

from _pytest.monkeypatch import MonkeyPatch

from elfienest.cli import admin_commands
from elfienest.operations.service_lifecycle import ServiceLifecycleResult


def test_start_managed_service_uses_normal_service_command(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    command = ("python", "scripts/serve.py", "--port", "8100")
    captured: list[tuple[str, ...]] = []

    def record_start(
        _home: Path,
        _root: Path,
        *,
        command: tuple[str, ...],
        health_checker: Callable[[], bool],
    ) -> ServiceLifecycleResult:
        captured.append(command)
        return ServiceLifecycleResult(status="started", command=command)

    monkeypatch.setattr(admin_commands, "get_elfie_home", lambda: tmp_path)
    monkeypatch.setattr(admin_commands, "start_service", record_start)

    result = admin_commands.start_managed_service(command)

    assert result.status == "started"
    assert captured == [command]
