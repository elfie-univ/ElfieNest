"""Protocol v3 WebSocket handling for the Godot runtime gateway."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, MutableSet
from typing import Any

import websockets
from pydantic import ValidationError

from infrastructure.godot.gateway.messages import (
    RuntimeEventFrame,
    parse_runtime_event_frame,
)
from infrastructure.godot.gateway.protocol import MessageRateLimiter
from infrastructure.godot.gateway.session import (
    RuntimeAuthorityError,
    RuntimeConnection,
    RuntimeQueueFullError,
    RuntimeSession,
    StaleRuntimeEventError,
)

logger = logging.getLogger("infrastructure.godot.gateway.api")
RuntimeEventReceiver = Callable[[RuntimeEventFrame], None]


class GodotProtocolV3Handler:
    """Handle an already-authenticated protocol v3 Godot connection."""

    def __init__(
        self,
        *,
        session: RuntimeSession,
        clients: MutableSet[Any],
        event_receiver: RuntimeEventReceiver,
    ) -> None:
        self._session = session
        self._clients = clients
        self._event_receiver = event_receiver

    async def handle(self, websocket: Any, hello_payload: dict[str, Any]) -> None:
        runtime_id = hello_payload.get("runtime_id")
        if not isinstance(runtime_id, str) or runtime_id == "":
            await websocket.close(4004, "Invalid Godot handshake")
            return
        try:
            connection = self._session.acquire_authority(runtime_id)
        except RuntimeAuthorityError as exc:
            await websocket.close(4008, str(exc))
            return

        self._clients.add(websocket)
        await websocket.send(self._hello_ok(connection))
        limiter = MessageRateLimiter()
        try:
            await self._receive_events(websocket, connection, limiter)
        finally:
            self._clients.discard(websocket)
            self._session.disconnect(connection)

    async def _receive_events(
        self,
        websocket: Any,
        connection: RuntimeConnection,
        limiter: MessageRateLimiter,
    ) -> None:
        try:
            async for message in websocket:
                if not limiter.allow():
                    await websocket.close(4029, "Message rate limit exceeded")
                    return
                if not await self._handle_message(websocket, connection, message):
                    return
        except websockets.exceptions.ConnectionClosed as exc:
            logger.info(
                "Godot v3 connection closed: %s (code=%s)",
                getattr(websocket, "remote_address", None),
                exc.code,
            )

    async def _handle_message(
        self,
        websocket: Any,
        connection: RuntimeConnection,
        message: str,
    ) -> bool:
        try:
            data = json.loads(message)
            if not isinstance(data, dict):
                await websocket.close(4002, "Invalid JSON object")
                return False
            event = parse_runtime_event_frame(data)
        except json.JSONDecodeError:
            await websocket.close(4002, "Invalid JSON")
            return False
        except ValidationError as exc:
            await websocket.close(
                4006, f"Invalid runtime event: {exc.errors()[0]['msg']}"
            )
            return False

        try:
            self._event_receiver(event)
        except StaleRuntimeEventError:
            await websocket.close(4007, "Stale runtime event")
            return False
        except RuntimeQueueFullError:
            await websocket.close(4030, "Runtime event queue full")
            return False
        return True

    @staticmethod
    def _hello_ok(connection: RuntimeConnection) -> str:
        return json.dumps(
            {
                "event": "hello_ok",
                "payload": {
                    "protocol": 3,
                    "runtime_id": connection.runtime_id,
                    "generation": connection.generation,
                },
            },
            ensure_ascii=False,
        )


__all__ = ("GodotProtocolV3Handler",)
