"""Characterize the existing protocol-v2 authority handshake before its rename."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anyio

from nest.godot_gateway.api import GodotAPIServer


class HandshakeWebSocket:
    """A finite in-memory WebSocket fixture for the protocol boundary."""

    def __init__(self, frames: list[str]) -> None:
        self.request = SimpleNamespace(headers={"Origin": "http://127.0.0.1:8000"})
        self._frames = frames
        self.sent: list[str] = []
        self.closed: list[tuple[int, str]] = []

    async def recv(self) -> str:
        return self._frames.pop(0)

    async def send(self, frame: str) -> None:
        self.sent.append(frame)

    async def close(self, code: int, reason: str) -> None:
        self.closed.append((code, reason))

    def __aiter__(self) -> HandshakeWebSocket:
        return self

    async def __anext__(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        raise StopAsyncIteration


def test_v2_authority_handshake_returns_runtime_generation() -> None:
    # Given: one same-origin Runtime presents the current v2 nonce handshake.
    websocket = HandshakeWebSocket(
        [
            json.dumps(
                {
                    "event": "hello",
                    "payload": {
                        "protocol": 2,
                        "nonce": "characterization-nonce",
                        "runtime_id": "characterization-runtime",
                    },
                }
            )
        ]
    )
    gateway = GodotAPIServer(port=0, handshake_nonce="characterization-nonce")

    # When: the authoritative Runtime connects through the real handler.
    anyio.run(gateway._handle_client, websocket)

    # Then: the v2 hello response carries the assigned authority generation.
    assert websocket.closed == []
    assert json.loads(websocket.sent[0]) == {
        "event": "hello_ok",
        "payload": {
            "protocol": 2,
            "runtime_id": "characterization-runtime",
            "generation": 1,
        },
    }
