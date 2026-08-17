from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import anyio
import pytest

from infrastructure.godot.gateway.api import GodotAPIServer


def test_gateway_start_propagates_bind_failure_detail(monkeypatch) -> None:
    server = GodotAPIServer(port=8765, handshake_nonce="nonce-1")

    def fail_startup() -> None:
        server._startup_error = OSError("address already in use")
        server._ready.set()

    monkeypatch.setattr(server, "_run_event_loop", fail_startup)

    with pytest.raises(
        RuntimeError,
        match="Godot Runtime gateway failed to start: address already in use",
    ):
        server.start()

    assert server._running is False


class FakeWebSocket:
    def __init__(self, messages: list[str], origin: str = "") -> None:
        self.request = SimpleNamespace(headers={"Origin": origin})
        self._messages = list(messages)
        self.sent: list[str] = []
        self.closed: list[tuple[int, str]] = []

    async def recv(self) -> str:
        return self._messages.pop(0)

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self, code: int, reason: str) -> None:
        self.closed.append((code, reason))

    def __aiter__(self) -> FakeWebSocket:
        return self

    async def __anext__(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        raise StopAsyncIteration


def test_gateway_accepts_only_authenticated_protocol_v3_hello() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    accepted = FakeWebSocket(
        [_hello(protocol=3, nonce="nonce-1")],
        origin="http://127.0.0.1:8000",
    )
    legacy = FakeWebSocket(
        [_hello(protocol=2, nonce="nonce-1")],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, accepted)
    anyio.run(server._handle_client, legacy)

    assert accepted.closed == []
    assert json.loads(accepted.sent[0])["payload"]["protocol"] == 3
    assert legacy.closed == [(4004, "Invalid Godot handshake")]
    assert legacy.sent == []


def test_gateway_rejects_event_as_first_frame() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        ['{"kind":"event","protocol":3}'],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == [(4003, "First frame must be hello")]


def test_gateway_rejects_wrong_nonce_and_origin() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    wrong_nonce = FakeWebSocket(
        [_hello(protocol=3, nonce="wrong")],
        origin="http://127.0.0.1:8000",
    )
    wrong_origin = FakeWebSocket(
        [_hello(protocol=3, nonce="nonce-1")],
        origin="https://example.invalid",
    )
    empty_origin = FakeWebSocket([_hello(protocol=3, nonce="nonce-1")])

    anyio.run(server._handle_client, wrong_nonce)
    anyio.run(server._handle_client, wrong_origin)
    anyio.run(server._handle_client, empty_origin)

    assert wrong_nonce.closed == [(4004, "Invalid Godot handshake")]
    assert wrong_origin.closed == [(4005, "Origin not allowed")]
    assert empty_origin.closed == [(4005, "Origin not allowed")]


def test_gateway_allows_configured_web_runtime_origin() -> None:
    server = GodotAPIServer(
        port=0,
        http_port=18000,
        handshake_nonce="nonce-1",
    )
    websocket = FakeWebSocket(
        [_hello(protocol=3, nonce="nonce-1")],
        origin="http://127.0.0.1:18000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == []


def test_gateway_restarts_fifty_times_without_leaking_thread_or_clients() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")

    for _ in range(50):
        server.start()
        server.stop()
        assert server._thread is not None
        assert not server._thread.is_alive()
        assert server.clients == set()


def test_gateway_can_take_over_a_core_reserved_socket() -> None:
    reserved = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    reserved.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    reserved.bind(("127.0.0.1", 0))
    reserved.listen(128)
    port = int(reserved.getsockname()[1])
    server = GodotAPIServer(
        port=port,
        handshake_nonce="nonce-1",
        prebound_socket=reserved,
    )

    server.start()
    try:
        assert server.port == port
        assert server._thread is not None
        assert server._thread.is_alive()
    finally:
        server.stop()


def _hello(*, protocol: int, nonce: str) -> str:
    return json.dumps(
        {
            "event": "hello",
            "payload": {
                "protocol": protocol,
                "nonce": nonce,
                "runtime_id": "runtime-a",
            },
        }
    )
