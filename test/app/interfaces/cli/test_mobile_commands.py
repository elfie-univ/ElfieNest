from __future__ import annotations

from dataclasses import dataclass

from app.features.operations import GetMobileAccessQuery, MobileAccessResult
from app.interfaces.cli import mobile_commands


@dataclass(frozen=True)
class FakePortStatus:
    name: str
    running: bool
    port: int


class FakeLifecycle:
    def default_port_statuses(self) -> tuple[FakePortStatus, ...]:
        return (FakePortStatus(name="HTTP", running=True, port=8000),)


class FakeOperations:
    def get_mobile_access(self, query: GetMobileAccessQuery) -> MobileAccessResult:
        assert query.http_port == 8000
        return MobileAccessResult(
            urls=("http://192.168.1.8:8000",),
            network_name="Elfie Home",
        )


def test_mobile_command_formats_feature_projection(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(mobile_commands, "clear_screen", lambda: None)
    monkeypatch.setattr(mobile_commands, "print_banner", lambda: None)
    monkeypatch.setattr(mobile_commands, "QRCODE_AVAILABLE", False)

    exit_code = mobile_commands.show_mobile_access(FakeLifecycle(), FakeOperations())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "URL: http://192.168.1.8:8000" in output
    assert "Network: Elfie Home" in output
    assert "Connect phone to: Elfie Home" in output


def test_mobile_command_reports_unavailable_network_from_feature(
    monkeypatch,
    capsys,
) -> None:
    class UnavailableOperations:
        def get_mobile_access(self, query: GetMobileAccessQuery) -> MobileAccessResult:
            return MobileAccessResult(urls=(), network_name=None)

    monkeypatch.setattr(mobile_commands, "clear_screen", lambda: None)
    monkeypatch.setattr(mobile_commands, "print_banner", lambda: None)

    exit_code = mobile_commands.show_mobile_access(
        FakeLifecycle(), UnavailableOperations()
    )

    assert exit_code == 1
    assert "Unable to get local IP address" in capsys.readouterr().out
