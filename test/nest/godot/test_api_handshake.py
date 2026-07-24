from __future__ import annotations

import json
from types import SimpleNamespace

import anyio

from nest.godot.api import GodotAPIServer


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


def test_gateway_accepts_only_authenticated_protocol_v2_hello() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    accepted = FakeWebSocket(
        [_hello(protocol=2, nonce="nonce-1")],
        origin="http://127.0.0.1:8000",
    )
    legacy = FakeWebSocket(
        [_hello(protocol=1, nonce="nonce-1")],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, accepted)
    anyio.run(server._handle_client, legacy)

    assert accepted.closed == []
    assert json.loads(accepted.sent[0])["payload"]["protocol"] == 2
    assert legacy.closed == [(4004, "Invalid Godot handshake")]
    assert legacy.sent == []


def test_gateway_rejects_event_as_first_frame() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        ['{"kind":"event","protocol":2}'],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == [(4003, "First frame must be hello")]


def test_gateway_rejects_wrong_nonce_and_origin() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    wrong_nonce = FakeWebSocket(
        [_hello(protocol=2, nonce="wrong")],
        origin="http://127.0.0.1:8000",
    )
    wrong_origin = FakeWebSocket(
        [_hello(protocol=2, nonce="nonce-1")],
        origin="https://example.invalid",
    )
    empty_origin = FakeWebSocket([_hello(protocol=2, nonce="nonce-1")])

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
        [_hello(protocol=2, nonce="nonce-1")],
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
