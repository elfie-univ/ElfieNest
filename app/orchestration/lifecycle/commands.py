"""Pure command parsing and identity rules for lifecycle workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Final, Sequence, Tuple

DEFAULT_SERVICE_PORTS: Final[Tuple[int, ...]] = (8000, 8765, 8766)
DEFAULT_HTTP_PORT: Final = 8000
DEFAULT_GODOT_WS_PORT: Final = 8765
DEFAULT_MANAGEMENT_WS_PORT: Final = 8766
INTERNAL_SERVICE_PORTS: Final[Tuple[int, ...]] = (8765,)
MANAGED_START_ENV: Final = "ELFIENEST_MANAGED_START"


def command_runs_service(
    command: Sequence[str], process_cwd: Path, expected_script: Path
) -> bool:
    """Identify absolute or cwd-relative scripts/serve.py arguments."""
    for argument in command[1:]:
        if argument in ("-c", "-m"):
            return False
        if argument and not argument.startswith("-"):
            return (process_cwd / argument).resolve() == expected_script
    return False


def restart_command_from_process(command: Sequence[str]) -> Tuple[str, ...]:
    """Preserve service arguments while removing the foreground-only --force flag."""
    return tuple(argument for argument in command if argument != "--force")


def http_port_from_command(command: Sequence[str]) -> int:
    """Read the HTTP port from a service command already validated by argparse."""
    for index, argument in enumerate(command):
        if argument.startswith("--port="):
            return int(argument.split("=", maxsplit=1)[1])
        if argument == "--port" and index + 1 < len(command):
            return int(command[index + 1])
    return DEFAULT_HTTP_PORT


def service_ports_from_command(command: Sequence[str]) -> Tuple[int, ...]:
    """Return the HTTP, Godot WebSocket and management WebSocket ports."""
    websocket_port = DEFAULT_MANAGEMENT_WS_PORT
    godot_ws_port = DEFAULT_GODOT_WS_PORT
    for index, argument in enumerate(command):
        if argument.startswith("--ws-port="):
            websocket_port = int(argument.split("=", maxsplit=1)[1])
        elif argument == "--ws-port" and index + 1 < len(command):
            websocket_port = int(command[index + 1])
        elif argument.startswith("--godot-ws-port="):
            godot_ws_port = int(argument.split("=", maxsplit=1)[1])
        elif argument == "--godot-ws-port" and index + 1 < len(command):
            godot_ws_port = int(command[index + 1])
    return (http_port_from_command(command), godot_ws_port, websocket_port)


def validate_service_ports(
    http_port: int,
    websocket_port: int,
    godot_ws_port: int = DEFAULT_GODOT_WS_PORT,
) -> str | None:
    """Validate externally configurable and fixed service ports."""
    ports = (http_port, websocket_port, godot_ws_port)
    if any(port < 1 or port > 65535 for port in ports):
        return "Ports must be in the 1-65535 range"
    if len(set(ports)) != len(ports):
        return "HTTP, management WebSocket, and Godot WebSocket ports must be distinct"
    return None
