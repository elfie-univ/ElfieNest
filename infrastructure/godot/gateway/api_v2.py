"""Protocol v2 WebSocket handling for the Godot runtime gateway."""

from __future__ import annotations

import json
import logging
from collections.abc import MutableSet
from typing import Any

import websockets
from pydantic import ValidationError

from infrastructure.godot.gateway.messages import parse_runtime_event_frame
from infrastructure.godot.gateway.protocol import MessageRateLimiter
from infrastructure.godot.gateway.session import (
    RuntimeAuthorityError,
    RuntimeConnection,
    RuntimeQueueFullError,
    RuntimeSession,
    StaleRuntimeEventError,
)

logger = logging.getLogger("infrastructure.godot.gateway.api")


class GodotProtocolV2Handler:
    """Handle an already-authenticated protocol v2 Godot connection."""

    def __init__(
        self,
        *,
        session: RuntimeSession,
        clients: MutableSet[Any],
    ) -> None:
        self._session = session
        self._clients = clients

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
                "👋 [通信网关] Godot v2 连接断开: %s (code=%s)",
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
            self._session.enqueue_event(event)
        except StaleRuntimeEventError:
            await websocket.close(4007, "Stale runtime event")
            return False
        except RuntimeQueueFullError:
            await websocket.close(4030, "Runtime event queue full")
            return False
        return True

    def _hello_ok(self, connection: RuntimeConnection) -> str:
        return json.dumps(
            {
                "event": "hello_ok",
                "payload": {
                    "protocol": 2,
                    "runtime_id": connection.runtime_id,
                    "generation": connection.generation,
                },
            },
            ensure_ascii=False,
        )
