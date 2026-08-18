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
        assert query.http_port == 15212
        return MobileAccessResult(
            urls=("http://192.168.1.8:15212",),
            network_name="Elfie Home",
        )


def test_mobile_command_formats_feature_projection(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(mobile_commands, "clear_screen", lambda: None)
    monkeypatch.setattr(mobile_commands, "QRCODE_AVAILABLE", False)

    exit_code = mobile_commands.show_mobile_access(
        FakeLifecycle(), FakeOperations(), http_port=15212
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Step 1: Connect your phone to this Wi-Fi network" in output
    assert "Step 2: Scan the QR code below with your phone" in output
    assert "URL: http://192.168.1.8:15212" in output
    assert "Network: Elfie Home" in output


def test_mobile_command_reports_unavailable_network_from_feature(
    monkeypatch,
    capsys,
) -> None:
    class UnavailableOperations:
        def get_mobile_access(self, query: GetMobileAccessQuery) -> MobileAccessResult:
            return MobileAccessResult(urls=(), network_name=None)

    monkeypatch.setattr(mobile_commands, "clear_screen", lambda: None)

    exit_code = mobile_commands.show_mobile_access(
        FakeLifecycle(), UnavailableOperations(), http_port=15212
    )

    assert exit_code == 1
    assert "Unable to get local IP address" in capsys.readouterr().out


def test_mobile_command_does_not_fall_back_to_the_default_port(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(mobile_commands, "clear_screen", lambda: None)

    exit_code = mobile_commands.show_mobile_access(
        FakeLifecycle(), FakeOperations(), http_port=None
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Service not running" in output
    assert "192.168.1.8:15212" not in output


def test_mobile_command_uses_explicit_port_and_prints_qr_steps(
    monkeypatch,
    capsys,
) -> None:
    class ExplicitPortOperations:
        def get_mobile_access(self, query: GetMobileAccessQuery) -> MobileAccessResult:
            assert query.http_port == 15212
            return MobileAccessResult(
                urls=("http://192.168.1.8:15212",),
                network_name="Elfie Home",
            )

    monkeypatch.setattr(mobile_commands, "QRCODE_AVAILABLE", True)

    exit_code = mobile_commands.show_mobile_access(
        FakeLifecycle(),
        ExplicitPortOperations(),
        http_port=15212,
        clear_terminal=False,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Step 1: Connect your phone to this Wi-Fi network" in output
    assert "Step 2: Scan the QR code below with your phone" in output
    assert "QR Code:" in output
    assert "URL: http://192.168.1.8:15212" in output
