from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class PortStatus:
    port: int
    name: str
    running: bool


def check_port(port: int, name: str, host: str = "127.0.0.1") -> PortStatus:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        running = sock.connect_ex((host, port)) == 0
    return PortStatus(port=port, name=name, running=running)


def default_port_statuses() -> List[PortStatus]:
    return service_port_statuses(8000, 8766)


def service_port_statuses(
    http_port: int,
    websocket_port: int,
    godot_ws_port: int = 8765,
) -> List[PortStatus]:
    return [
        check_port(http_port, "HTTP"),
        check_port(websocket_port, "WebSocket (admin)"),
        check_port(godot_ws_port, "WebSocket (Godot)"),
    ]
