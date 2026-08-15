from __future__ import annotations

from subprocess import CompletedProcess

from infrastructure.platform import mobile_network
from infrastructure.platform.mobile_network import PlatformMobileNetworkAdapter


def test_adapter_prefers_a_lan_address_over_vpn_interfaces(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "inet 127.0.0.1 netmask 0xff000000\n"
                "inet 198.18.0.1 netmask 0xffff0000\n"
                "inet 10.0.0.4 netmask 0xffffff00\n"
                "inet 192.168.1.8 netmask 0xffffff00\n"
            ),
        )

    monkeypatch.setattr(mobile_network.subprocess, "run", fake_run)

    assert PlatformMobileNetworkAdapter().preferred_lan_address() == "192.168.1.8"


def test_adapter_reads_the_current_macos_wifi_name(monkeypatch) -> None:
    monkeypatch.setattr(mobile_network.platform, "system", lambda: "Darwin")

    def fake_run(command, **kwargs):
        _ = kwargs
        if command[-1] == "-listallhardwareports":
            return CompletedProcess(
                args=command,
                returncode=0,
                stdout="Hardware Port: Wi-Fi\nDevice: en7\n",
            )
        if command[-2:] == ["-getairportnetwork", "en7"]:
            return CompletedProcess(
                args=command,
                returncode=0,
                stdout="Current Wi-Fi Network: Elfie Home\n",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(mobile_network.subprocess, "run", fake_run)

    assert PlatformMobileNetworkAdapter().current_wifi_name() == "Elfie Home"


def test_adapter_prefers_the_visible_macos_networksetup_name(
    monkeypatch,
) -> None:
    monkeypatch.setattr(mobile_network.platform, "system", lambda: "Darwin")

    def fake_run(command, **kwargs):
        _ = kwargs
        if command[-1] == "-listallhardwareports":
            return CompletedProcess(
                args=command,
                returncode=0,
                stdout="Hardware Port: Wi-Fi\nDevice: en0\n",
            )
        if command[-2:] == ["-getairportnetwork", "en0"]:
            return CompletedProcess(
                args=command,
                returncode=0,
                stdout="Current Wi-Fi Network: Dd House_guest\n",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(mobile_network.subprocess, "run", fake_run)

    assert PlatformMobileNetworkAdapter().current_wifi_name() == "Dd House_guest"


def test_adapter_reads_the_current_windows_wifi_name(monkeypatch) -> None:
    monkeypatch.setattr(mobile_network.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        mobile_network.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="    Name                   : Wi-Fi\n    SSID                   : Elfie Home\n    BSSID                  : aa:bb:cc:dd:ee:ff\n",
        ),
    )

    assert PlatformMobileNetworkAdapter().current_wifi_name() == "Elfie Home"


def test_adapter_returns_none_when_wifi_name_is_redacted(monkeypatch) -> None:
    monkeypatch.setattr(mobile_network.platform, "system", lambda: "Darwin")

    def fake_run(command, **kwargs):
        _ = kwargs
        if command[-1] == "-listallhardwareports":
            return CompletedProcess(
                args=command,
                returncode=0,
                stdout="Hardware Port: Wi-Fi\nDevice: en0\n",
            )
        if command[-2:] == ["-getairportnetwork", "en0"]:
            return CompletedProcess(
                args=command,
                returncode=0,
                stdout="Current Wi-Fi Network: <redacted>\n",
            )
        if command[-1] == "SPAirPortDataType":
            return CompletedProcess(
                args=command,
                returncode=0,
                stdout="Current Network Information:\n    <redacted>:\n",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(mobile_network.subprocess, "run", fake_run)

    assert PlatformMobileNetworkAdapter().current_wifi_name() is None
