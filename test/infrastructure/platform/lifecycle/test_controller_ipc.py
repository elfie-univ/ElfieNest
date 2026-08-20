from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from infrastructure.platform.lifecycle.controller_ipc import (
    CONTROLLER_SOCKET_FILENAME,
    CONTROLLER_TOKEN_FILENAME,
    ControllerIpcError,
    LocalControllerIpcAdapter,
)


@pytest.mark.skipif(os.name == "nt", reason="POSIX socket transport only")
def test_local_controller_ipc_sends_authenticated_command() -> None:
    token = "token-for-test"
    tmp_path = Path(tempfile.mkdtemp(prefix="enipc-", dir="/tmp"))
    socket_path = tmp_path / CONTROLLER_SOCKET_FILENAME
    (tmp_path / CONTROLLER_TOKEN_FILENAME).write_text(f"{token}\n", encoding="utf-8")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(1)
    received: dict[str, object] = {}

    def serve_once() -> None:
        connection, _ = server.accept()
        with connection:
            received.update(json.loads(connection.recv(4096).decode("utf-8")))
            connection.sendall(b'{"ok":true,"result":{"accepted":true}}\n')

    worker = threading.Thread(target=serve_once)
    worker.start()
    try:
        result = LocalControllerIpcAdapter(home=tmp_path).request(
            "ENSURE_SERVER", {"source": "test"}
        )
    finally:
        worker.join(timeout=2.0)
        server.close()
        shutil.rmtree(tmp_path, ignore_errors=True)

    assert result == {"accepted": True}
    assert received == {
        "protocol": 2,
        "token": token,
        "command": "ENSURE_SERVER",
        "payload": {"source": "test"},
    }


def test_local_controller_ipc_returns_none_when_controller_is_absent(
    tmp_path: Path,
) -> None:
    assert LocalControllerIpcAdapter(home=tmp_path).request("STATUS") is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX socket transport only")
def test_local_controller_ipc_surfaces_an_authenticated_rejection() -> None:
    token = "token-for-test"
    tmp_path = Path(tempfile.mkdtemp(prefix="enipc-", dir="/tmp"))
    socket_path = tmp_path / CONTROLLER_SOCKET_FILENAME
    (tmp_path / CONTROLLER_TOKEN_FILENAME).write_text(f"{token}\n", encoding="utf-8")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(1)

    def serve_once() -> None:
        connection, _ = server.accept()
        with connection:
            connection.recv(4096)
            connection.sendall(b'{"ok":false,"error":"not allowed"}\n')

    worker = threading.Thread(target=serve_once)
    worker.start()
    try:
        try:
            LocalControllerIpcAdapter(home=tmp_path).request("STOP_SERVER")
        except ControllerIpcError as error:
            assert str(error) == "not allowed"
        else:
            raise AssertionError("Controller rejection was swallowed")
    finally:
        worker.join(timeout=2.0)
        server.close()
        shutil.rmtree(tmp_path, ignore_errors=True)
