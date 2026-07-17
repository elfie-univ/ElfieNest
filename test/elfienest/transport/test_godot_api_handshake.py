from __future__ import annotations

from types import SimpleNamespace

import anyio

from elfienest.transport.godot_api import GodotAPIServer


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
        ]
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
        ['{"event":"runtime_ready","payload":{"protocol":1}}']
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
        ['{"event":"hello","payload":{"protocol":1,"nonce":"wrong"}}']
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
