"""Mobile access commands: display URL and QR code."""

from __future__ import annotations

from typing import Optional

from app.features.operations import GetMobileAccessQuery, OperationsFacade
from app.interfaces.cli.tui.common import clear_screen, print_banner
from app.orchestration.lifecycle import LifecycleFacade

try:
    import qrcode
    import qrcode.constants

    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False


def show_mobile_access(
    lifecycle: LifecycleFacade,
    operations: OperationsFacade,
    *,
    http_port: Optional[int] = None,
    clear_terminal: bool = True,
) -> int:
    if clear_terminal:
        clear_screen()
    print_banner()

    print("  📱 Mobile Access")
    print("  " + "=" * 45)
    print()

    if http_port is None:
        print("  ⚠️  Service not running")
        print("  Start service first: elfienest start")
        print()
        return 1

    access = operations.get_mobile_access(GetMobileAccessQuery(http_port=http_port))
    if not access.urls:
        print("  ❌ Unable to get local IP address")
        print("  Check network connection")
        print()
        return 1

    url = access.urls[0]
    wifi_name = access.network_name

    print("  Step 1: Connect your phone to this Wi-Fi network")
    if wifi_name:
        if wifi_name == "<redacted>":
            print("  Network: WiFi Connected (name hidden by system)")
        else:
            print(f"  Network: {wifi_name}")
    else:
        print("  Network: Use the same Wi-Fi network as this computer")
    print()

    print("  Step 2: Scan the QR code below with your phone")
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
    else:
        print("  💡 Install qrcode library to show QR code:")
        print("     uv pip install qrcode[pil]")
        print()
    print(f"  URL: {url}")
    print()

    return 0
