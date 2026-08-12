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
        try:
            if platform.system() == "Darwin":
                network_name = self._macos_wifi_name()
                if network_name is not None:
                    return network_name
                return self._macos_networksetup_name()
            if platform.system() == "Linux":
                result = subprocess.run(
                    ["iwgetid", "-r"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                return result.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None
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
            ["system_profiler", "SPAirPortDataType"],
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
            if "<redacted>" in next_line:
                return "<redacted>"
            if ":" in next_line:
                return next_line.split(":", 1)[0].strip() or None
        return None

    @staticmethod
    def _macos_networksetup_name() -> Optional[str]:
        result = subprocess.run(
            ["networksetup", "-getairportnetwork", "en0"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        output = result.stdout.strip()
        if "Current Wi-Fi Network:" not in output:
            return None
        return output.split("Current Wi-Fi Network:", 1)[1].strip() or None


__all__ = ("PlatformMobileNetworkAdapter",)
