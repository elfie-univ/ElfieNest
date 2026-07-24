from __future__ import annotations

import json
from datetime import datetime, timezone
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


def test_protocol_v2_world_ready_enters_runtime_queue() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    websocket = FakeWebSocket(
        [
            _hello("runtime-a"),
            _event("evt-1", "runtime-a", 1, "world_ready", 3, {"ready": True}),
        ],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == []
    assert json.loads(websocket.sent[0])["payload"] == {
        "protocol": 2,
        "runtime_id": "runtime-a",
        "generation": 1,
    }
    drained = server.drain_runtime_events()
    assert [event.message_id for event in drained] == ["evt-1"]
    assert server.runtime_ready is False


def test_protocol_v2_rejects_second_live_runtime() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    connection = server.runtime_session.acquire_authority("runtime-a")
    websocket = FakeWebSocket(
        [_hello("runtime-b")],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == [(4008, "runtime runtime-a already owns authority")]
    assert server.runtime_session.active == connection


def test_protocol_v2_closes_when_runtime_queue_is_full() -> None:
    server = GodotAPIServer(port=0, handshake_nonce="nonce-1")
    server.runtime_session = server.runtime_session.__class__(max_queue_size=1)
    websocket = FakeWebSocket(
        [
            _hello("runtime-a"),
            _event("evt-1", "runtime-a", 1, "world_ready", 0, {"ready": True}),
            _event(
                "evt-2",
                "runtime-a",
                1,
                "world_snapshot",
                0,
                {"world_revision": 0, "actors": []},
            ),
        ],
        origin="http://127.0.0.1:8000",
    )

    anyio.run(server._handle_client, websocket)

    assert websocket.closed == [(4030, "Runtime event queue full")]
    assert server.runtime_session.dropped_event_count == 1


def _hello(runtime_id: str) -> str:
    return json.dumps(
        {
            "event": "hello",
            "payload": {
                "protocol": 2,
                "nonce": "nonce-1",
                "runtime_id": runtime_id,
            },
        }
    )


def _event(
    message_id: str,
    runtime_id: str,
    generation: int,
    name: str,
    world_revision: int,
    payload: dict[str, object],
) -> str:
    return json.dumps(
        {
            "kind": "event",
            "protocol": 2,
            "name": name,
            "message_id": message_id,
            "runtime_id": runtime_id,
            "generation": generation,
            "world_revision": world_revision,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
    )
