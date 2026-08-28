"""Authenticated local client for the packaged Desktop Controller."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Mapping, Optional

from pydantic import JsonValue

CONTROLLER_NAMESPACE = "elfienest.desktop-ui"
CONTROLLER_TOKEN_FILENAME = "controller.token"
CONTROLLER_SOCKET_FILENAME = "controller.sock"
CONTROLLER_ENDPOINT_FILENAME = "controller.endpoint.json"
CONTROLLER_PROTOCOL_VERSION = 2
CONTROLLER_TIMEOUT_SECONDS = 2.0
_MAX_FRAME_BYTES = 64 * 1024


class ControllerIpcError(RuntimeError):
    """The Controller answered but rejected or malformed a command."""


def controller_home() -> Path:
    """Return the stable per-user Controller directory used by Electron."""
    configured_app_data = os.environ.get("ELFIENEST_DESKTOP_APP_DATA", "").strip()
    if configured_app_data:
        base = Path(configured_app_data).expanduser()
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        ).expanduser()
    return (base / "ElfieNest" / CONTROLLER_NAMESPACE).resolve()


class LocalControllerIpcAdapter:
    """Use a short-lived authenticated local connection for one command."""

    def __init__(
        self,
        *,
        home: Optional[Path] = None,
        timeout_seconds: float = CONTROLLER_TIMEOUT_SECONDS,
    ) -> None:
        self._home = home
        self._timeout_seconds = max(0.1, timeout_seconds)

    def request(
        self,
        command: str,
        payload: Optional[Mapping[str, JsonValue]] = None,
    ) -> Optional[Mapping[str, JsonValue]]:
        if not command or any(character in command for character in "\r\n"):
            raise ControllerIpcError("Controller command is invalid")
        home = (self._home or controller_home()).resolve()
        try:
            token = (
                (home / CONTROLLER_TOKEN_FILENAME).read_text(encoding="utf-8").strip()
            )
            target = self._target(home)
        except (FileNotFoundError, OSError, ValueError):
            return None
        if not token or target is None:
            return None

        frame = {
            "protocol": CONTROLLER_PROTOCOL_VERSION,
            "token": token,
            "command": command,
            "payload": dict(payload or {}),
        }
        try:
            with self._connect(target) as connection:
                connection.sendall(
                    (json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8")
                )
                raw = self._read_frame(connection)
        except (ConnectionRefusedError, FileNotFoundError, TimeoutError, OSError):
            return None

        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ControllerIpcError("Controller response is not valid JSON") from error
        if not isinstance(response, dict):
            raise ControllerIpcError("Controller response must be an object")
        if response.get("ok") is not True:
            detail = response.get("error")
            raise ControllerIpcError(
                str(detail)
                if isinstance(detail, str)
                else "Controller rejected command"
            )
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise ControllerIpcError("Controller result must be an object")
        return result

    @staticmethod
    def _target(home: Path) -> tuple[str, str, int] | tuple[str, str] | None:
        if os.name != "nt":
            return ("unix", str(home / CONTROLLER_SOCKET_FILENAME))
        try:
            endpoint = json.loads(
                (home / CONTROLLER_ENDPOINT_FILENAME).read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return None
        if (
            not isinstance(endpoint, dict)
            or endpoint.get("transport") != "tcp"
            or endpoint.get("host") != "127.0.0.1"
            or not isinstance(endpoint.get("port"), int)
        ):
            return None
        port = endpoint["port"]
        if not 1 <= port <= 65535:
            return None
        return ("tcp", "127.0.0.1", port)

    def _connect(
        self,
        target: tuple[str, str, int] | tuple[str, str],
    ) -> socket.socket:
        if len(target) == 2:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.settimeout(self._timeout_seconds)
            connection.connect(target[1])
            return connection
        _, host, port = target
        connection = socket.create_connection(
            (host, port), timeout=self._timeout_seconds
        )
        connection.settimeout(self._timeout_seconds)
        return connection

    @staticmethod
    def _read_frame(connection: socket.socket) -> bytes:
        data = bytearray()
        while len(data) < _MAX_FRAME_BYTES:
            chunk = connection.recv(min(4096, _MAX_FRAME_BYTES - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b"\n" in chunk:
                break
        frame = bytes(data).split(b"\n", 1)[0]
        if not frame:
            raise ControllerIpcError("Controller returned an empty response")
        if len(frame) > _MAX_FRAME_BYTES:
            raise ControllerIpcError("Controller response is too large")
        return frame


__all__ = (
    "CONTROLLER_ENDPOINT_FILENAME",
    "CONTROLLER_NAMESPACE",
    "CONTROLLER_PROTOCOL_VERSION",
    "CONTROLLER_SOCKET_FILENAME",
    "CONTROLLER_TIMEOUT_SECONDS",
    "CONTROLLER_TOKEN_FILENAME",
    "ControllerIpcError",
    "LocalControllerIpcAdapter",
    "controller_home",
)
