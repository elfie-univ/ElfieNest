"""Mobile access commands: display URL and QR code."""

from __future__ import annotations

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
) -> int:
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

    access = operations.get_mobile_access(GetMobileAccessQuery(http_port=http_port))
    if not access.urls:
        print("  ❌ Unable to get local IP address")
        print("  Check network connection")
        print()
        return 1

    url = access.urls[0]
    wifi_name = access.network_name

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
