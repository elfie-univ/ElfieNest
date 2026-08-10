"""Mobile access commands: display URL and QR code."""

from __future__ import annotations

import platform
import socket
import subprocess

from app.interfaces.cli.tui.common import clear_screen, print_banner
from app.orchestration.lifecycle import LifecycleFacade

try:
    import qrcode
    import qrcode.constants

    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False


def show_mobile_access(lifecycle: LifecycleFacade) -> int:
    clear_screen()
    print_banner()

    print("  📱 Mobile Access")
    print("  " + "=" * 45)
    print()

    port_statuses = lifecycle.default_port_statuses()

    http_port = None
    for status in port_statuses:
        if status.name == "HTTP" and status.running:
            http_port = status.port
            break

    if http_port is None:
        print("  ⚠️  Service not running")
        print("  Start service first: elfienest start")
        print()
        return 1

    local_ip = _get_local_ip()

    if local_ip is None:
        print("  ❌ Unable to get local IP address")
        print("  Check network connection")
        print()
        return 1

    url = f"http://{local_ip}:{http_port}"
    wifi_name = _get_current_wifi()

    print(f"  URL: {url}")
    if wifi_name:
        if wifi_name == "<redacted>":
            print("  Network: WiFi Connected (name hidden by system)")
        else:
            print(f"  Network: {wifi_name}")
    print()

    if QRCODE_AVAILABLE:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)

        print("  QR Code:")
        print()
        matrix = qr.get_matrix()
        for row in matrix:
            line = "     "
            for cell in row:
                line += "██" if cell else "  "
            print(line)
        print()
        print("  📷 Scan QR code or enter URL to access")
    else:
        print("  💡 Install qrcode library to show QR code:")
        print("     uv pip install qrcode[pil]")
        print()
        print(f"  Enter this URL on your phone: {url}")

    print()
    if wifi_name:
        if wifi_name == "<redacted>":
            print("  ℹ️  Phone and computer should be on the same WiFi network")
        else:
            print(f"  ℹ️  Connect phone to: {wifi_name}")
    else:
        print("  ⚠️  Ensure phone and computer are on the same network")
    print()

    return 0


def _get_local_ip() -> str | None:
    """Get local IP address, preferring real LAN interfaces over VPN/USB."""
    try:
        import subprocess

        result = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        output = result.stdout

        import re

        ips = []
        for match in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)", output):
            ip = match.group(1)
            if ip.startswith("127."):
                continue
            if ip.startswith("198.18."):
                continue
            if ip.startswith("10."):
                ips.append(ip)
            elif ip.startswith("192.168."):
                ips.append(ip)
            elif ip.startswith("172."):
                next_octet = int(ip.split(".")[1])
                if 16 <= next_octet <= 31:
                    ips.append(ip)

        if ips:
            lan_ips = [ip for ip in ips if ip.startswith("192.168.")]
            return lan_ips[0] if lan_ips else ips[0]

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            local_ip = str(sock.getsockname()[0])
            return local_ip
    except (OSError, subprocess.SubprocessError):
        return None


def _get_current_wifi() -> str | None:
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["system_profiler", "SPAirPortDataType"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if (
                result.returncode == 0
                and "Current Network Information:" in result.stdout
            ):
                lines = result.stdout.split("\n")
                for i, line in enumerate(lines):
                    if "Current Network Information:" in line and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if ":" in next_line:
                            network_name = next_line.split(":")[0].strip()
                            if network_name and network_name not in ("", "<redacted>"):
                                return network_name
                        if "<redacted>" in next_line:
                            return "<redacted>"

            result = subprocess.run(
                ["networksetup", "-getairportnetwork", "en0"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            output = result.stdout.strip()
            if "Current Wi-Fi Network:" in output:
                wifi_name = output.split("Current Wi-Fi Network:")[-1].strip()
                return wifi_name if wifi_name else None
        elif system == "Linux":
            result = subprocess.run(
                ["iwgetid", "-r"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            wifi_name = result.stdout.strip()
            return wifi_name if wifi_name else None
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    return None
