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
    monkeypatch.setattr(
        mobile_network.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="Current Network Information:\n    Elfie Home:\n",
        ),
    )

    assert PlatformMobileNetworkAdapter().current_wifi_name() == "Elfie Home"
