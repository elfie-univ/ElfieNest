"""Operating-system adapter for mobile LAN access projection."""

from __future__ import annotations

import platform
import re
import socket
import subprocess
from typing import Optional


class PlatformMobileNetworkAdapter:
    def preferred_lan_address(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["ifconfig"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            addresses = self._private_addresses(result.stdout)
            if addresses:
                lan_addresses = tuple(
                    address for address in addresses if address.startswith("192.168.")
                )
                return (lan_addresses or addresses)[0]

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return str(sock.getsockname()[0])
        except (OSError, subprocess.SubprocessError):
            return None

    def current_wifi_name(self) -> Optional[str]:
        system = platform.system()
        lookups = {
            "Darwin": (self._macos_networksetup_name, self._macos_wifi_name),
            "Windows": (self._windows_wifi_name,),
            "Linux": (self._linux_wifi_name,),
        }.get(system, ())
        for lookup in lookups:
            try:
                network_name = self._usable_wifi_name(lookup())
            except (OSError, subprocess.SubprocessError):
                continue
            if network_name is not None:
                return network_name
        return None

    @staticmethod
    def _private_addresses(output: str) -> tuple[str, ...]:
        addresses = []
        for match in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)", output):
            address = match.group(1)
            if address.startswith(("127.", "198.18.")):
                continue
            if address.startswith(("10.", "192.168.")):
                addresses.append(address)
                continue
            if address.startswith("172."):
                second_octet = int(address.split(".")[1])
                if 16 <= second_octet <= 31:
                    addresses.append(address)
        return tuple(addresses)

    @staticmethod
    def _macos_wifi_name() -> Optional[str]:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPAirPortDataType"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if (
            result.returncode != 0
            or "Current Network Information:" not in result.stdout
        ):
            return None
        lines = result.stdout.splitlines()
        for index, line in enumerate(lines):
            if "Current Network Information:" not in line or index + 1 >= len(lines):
                continue
            next_line = lines[index + 1].strip()
            if ":" in next_line:
                return next_line.split(":", 1)[0].strip() or None
        return None

    @staticmethod
    def _macos_networksetup_name() -> Optional[str]:
        interfaces_result = subprocess.run(
            ["/usr/sbin/networksetup", "-listallhardwareports"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if interfaces_result.returncode != 0:
            return None
        for interface in PlatformMobileNetworkAdapter._macos_wifi_interfaces(
            interfaces_result.stdout
        ):
            result = subprocess.run(
                ["/usr/sbin/networksetup", "-getairportnetwork", interface],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            output = result.stdout.strip()
            if result.returncode == 0 and "Current Wi-Fi Network:" in output:
                return output.split("Current Wi-Fi Network:", 1)[1].strip() or None
        return None

    @staticmethod
    def _macos_wifi_interfaces(output: str) -> tuple[str, ...]:
        interfaces = []
        is_wifi = False
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("Hardware Port:"):
                port_name = stripped.split(":", 1)[1].strip()
                is_wifi = port_name in {"Wi-Fi", "AirPort"}
                continue
            if is_wifi and stripped.startswith("Device:"):
                interface = stripped.split(":", 1)[1].strip()
                if interface:
                    interfaces.append(interface)
                is_wifi = False
        return tuple(interfaces)

    @staticmethod
    def _windows_wifi_name() -> Optional[str]:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            match = re.match(r"^\s*SSID\s*:\s*(.*?)\s*$", line)
            if match:
                return match.group(1) or None
        return None

    @staticmethod
    def _linux_wifi_name() -> Optional[str]:
        result = subprocess.run(
            ["iwgetid", "-r"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "device", "wifi"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1].replace(r"\:", ":") or None
        return None

    @staticmethod
    def _usable_wifi_name(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or normalized.casefold() == "<redacted>":
            return None
        return normalized


__all__ = ("PlatformMobileNetworkAdapter",)
