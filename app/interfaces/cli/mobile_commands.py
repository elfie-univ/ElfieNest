"""Mobile access commands: display URL and QR code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.features.operations import GetMobileAccessQuery, OperationsFacade
from app.interfaces.cli.tui.common import clear_screen
from app.orchestration.lifecycle import BackendTier, LifecycleFacade, RuntimeComponent

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
    data_home: Optional[Path] = None,
    display_home: Optional[str] = None,
    clear_terminal: bool = False,
) -> int:
    if clear_terminal:
        clear_screen()
    print("  📱 Mobile access")
    if data_home is not None:
        print(f"  Data: {display_home or _short_data_home(data_home)}")

    projection = None
    if data_home is not None:
        try:
            projection = lifecycle.runtime_projection(data_home)
        except (AttributeError, OSError, RuntimeError, ValueError):
            projection = None
    if data_home is not None and (
        projection is None or projection.tier is BackendTier.OFFLINE
    ):
        http_port = None
    elif data_home is not None and http_port is not None:
        try:
            health = lifecycle.http_get(
                f"http://127.0.0.1:{http_port}/api/health",
                timeout_seconds=2.0,
            )
        except (AttributeError, OSError, TimeoutError, RuntimeError, ValueError):
            http_port = None
        else:
            identity_matches = False
            if health.status == 200:
                try:
                    payload = json.loads(health.body.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    payload = None
                identity_matches = (
                    projection is not None
                    and isinstance(payload, dict)
                    and payload.get("status") == "ok"
                    and payload.get("instance_id") == projection.instance_id
                    and payload.get("generation") == projection.generation
                )
            if not identity_matches:
                http_port = None
    if (
        projection is not None
        and projection.tier is not BackendTier.OFFLINE
        and http_port is not None
    ):
        pids = []
        for component, label in (
            (RuntimeComponent.CORE, "core"),
            (RuntimeComponent.GATEWAY, "gateway"),
            (RuntimeComponent.GODOT_AUTHORITY, "godot"),
        ):
            pid = projection.component(component).pid
            if pid is not None:
                pids.append(f"{label}={pid}")
        if pids:
            print(f"  PID: {' · '.join(pids)}")
        ports = {endpoint.name: endpoint.port for endpoint in projection.endpoints}
        if "http" in ports and "godot_ws" in ports:
            print(f"  Ports: HTTP={ports['http']} · WS={ports['godot_ws']}")
    elif http_port is not None:
        print(f"  Ports: HTTP={http_port}")

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
            print("  Network: Wi-Fi connected (name hidden by system)")
        else:
            print(f"  Network: {wifi_name}")
    else:
        print("  Network: use the same Wi-Fi network as this computer")

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

    return 0


def _short_data_home(data_home: Path) -> str:
    canonical = data_home.expanduser().resolve(strict=False)
    for base, prefix in (
        (Path.cwd().resolve(), ""),
        (Path.home().resolve(), "~/"),
    ):
        try:
            relative = canonical.relative_to(base)
        except ValueError:
            continue
        relative_text = str(relative)
        return f"{prefix}{relative_text}" if relative_text != "." else (prefix or ".")
    return str(canonical)
