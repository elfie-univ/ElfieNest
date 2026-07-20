from __future__ import annotations

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


def test_godot_requires_hello_nonce_before_runtime_events() -> None:
    # Given
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        [
            '{"event":"hello","payload":{"protocol":1,"nonce":"nonce-1"}}',
            '{"event":"runtime_ready","payload":{"protocol":1}}',
        ],
        origin="http://127.0.0.1:8000",
    )

    # When
    anyio.run(server._handle_client, websocket)

    # Then
    assert websocket.closed == []
    assert '"event": "hello_ok"' in websocket.sent[0]


def test_godot_rejects_runtime_event_as_first_frame() -> None:
    # Given
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        ['{"event":"runtime_ready","payload":{"protocol":1}}'],
        origin="http://127.0.0.1:8000",
    )

    # When
    anyio.run(server._handle_client, websocket)

    # Then
    assert websocket.closed == [(4003, "First frame must be hello")]
    assert websocket.sent == []


def test_godot_rejects_wrong_nonce_and_origin() -> None:
    # Given
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    wrong_nonce = FakeWebSocket(
        ['{"event":"hello","payload":{"protocol":1,"nonce":"wrong"}}'],
        origin="http://127.0.0.1:8000",
    )
    wrong_origin = FakeWebSocket(
        ['{"event":"hello","payload":{"protocol":1,"nonce":"nonce-1"}}'],
        origin="https://example.invalid",
    )

    # When
    anyio.run(server._handle_client, wrong_nonce)
    anyio.run(server._handle_client, wrong_origin)

    # Then
    assert wrong_nonce.closed == [(4004, "Invalid Godot handshake")]
    assert wrong_origin.closed == [(4005, "Origin not allowed")]


def test_godot_rejects_empty_origin() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        ['{"event":"hello","payload":{"protocol":1,"nonce":"nonce-1"}}']
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == [(4005, "Origin not allowed")]


def test_godot_rejects_unknown_runtime_event() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        [
            '{"event":"hello","payload":{"protocol":1,"nonce":"nonce-1"}}',
            '{"event":"not_allowed","payload":{}}',
        ],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == [(4006, "Event not allowed")]


def test_godot_closes_connection_after_rate_limit() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    messages = [
        '{"event":"hello","payload":{"protocol":1,"nonce":"nonce-1"}}'
    ] + ['{"event":"runtime_ready","payload":{"protocol":1}}'] * 61
    websocket = FakeWebSocket(messages, origin="http://127.0.0.1:8000")

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == [(4029, "Message rate limit exceeded")]


def test_godot_allows_configured_management_ui_origin() -> None:
    server = GodotAPIServer(port=0, http_port=18000, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        ['{"event":"hello","payload":{"protocol":1,"nonce":"nonce-1"}}'],
        origin="http://127.0.0.1:18000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == []
