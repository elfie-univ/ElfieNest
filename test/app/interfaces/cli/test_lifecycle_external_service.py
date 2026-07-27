from __future__ import annotations

from pathlib import Path
from typing import Tuple

from app.features.administration.system_service import PortStatus
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle.process import PID_FILENAME


class ExternalInspector:
    """Process inspector fixture for a live service from another checkout."""

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd

    def exists(self, pid: int) -> bool:
        return pid == 15727

    def cwd(self, pid: int) -> Path:
        if pid != 15727:
            raise OSError("unexpected pid")
        return self._cwd

    def command(self, pid: int) -> Tuple[str, ...]:
        if pid != 15727:
            raise OSError("unexpected pid")
        return ("python", "scripts/serve.py", "--fallback")


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
    monkeypatch.setattr(lifecycle_commands, "get_elfie_home", lambda: elfie_home)
    monkeypatch.setattr(
        lifecycle_commands, "existing_service_command", lambda *args: None
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "DefaultProcessInspector",
        lambda: ExternalInspector(external_root),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "default_port_statuses",
        lambda: [PortStatus(port=8000, name="HTTP", running=True)],
    )

    # When: the user asks for status from the current worktree.
    lifecycle_commands.show_service_status()

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
    monkeypatch.setattr(
        lifecycle_commands, "existing_service_command", lambda *args: None
    )
    monkeypatch.setattr(
        lifecycle_commands, "_web_is_healthy", lambda port=8000: port == 8000
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda: start_calls.append("start"),
    )

    # When: the user runs `web`.
    result = lifecycle_commands.open_web_console()

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
    monkeypatch.setattr(
        lifecycle_commands, "existing_service_command", lambda *args: None
    )
    monkeypatch.setattr(lifecycle_commands, "_web_is_healthy", lambda port=8000: False)
    monkeypatch.setattr(
        lifecycle_commands,
        "default_port_statuses",
        lambda: [PortStatus(port=8000, name="HTTP", running=True)],
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda: start_calls.append("start"),
    )

    # When: the user runs `web`.
    result = lifecycle_commands.open_web_console()

    # Then: the CLI reports the external owner class instead of starting again.
    assert result.status == "failed"
    assert opened == []
    assert start_calls == []
    assert "occupied by external process" in capsys.readouterr().out
