"""Threaded WebSocket gateway for the Godot protocol v2 runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import threading
from typing import Any, cast

import websockets

from infrastructure.godot.body_transport import RuntimeIntentPayload
from infrastructure.godot.gateway.api_v2 import GodotProtocolV2Handler
from infrastructure.godot.gateway.messages import (
    CommandName,
    JsonObject,
    RuntimeEventFrame,
)
from infrastructure.godot.gateway.session import (
    RuntimeConnection,
    RuntimeSession,
    RuntimeSessionNotReadyError,
)

logger = logging.getLogger("infrastructure.godot.gateway.api")
GODOT_PROTOCOL_VERSION = 2


class GodotAPIServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        http_port: int = 8000,
        handshake_nonce: str | None = None,
        allowed_origins: set[str] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.http_port = http_port
        self.handshake_nonce = (
            handshake_nonce
            or os.environ.get("ELFIENEST_GODOT_NONCE", "")
            or secrets.token_urlsafe(32)
        )
        self.allowed_origins = (
            allowed_origins
            if allowed_origins is not None
            else {
                f"http://127.0.0.1:{http_port}",
                f"http://localhost:{http_port}",
            }
        )
        self.clients: set[Any] = set()
        self.runtime_session = RuntimeSession()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: Any = None
        self._running = False
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._ready.clear()
        self._startup_error = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_event_loop,
            daemon=True,
            name="ElfieNest_WS_Thread",
        )
        self._thread.start()
        if not self._ready.wait(timeout=3.0):
            logger.error("Godot Runtime gateway did not become ready within 3 seconds")
            return
        if self._startup_error is not None:
            self._running = False
            raise RuntimeError(
                "Godot Runtime gateway failed to start"
            ) from self._startup_error

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run_event_loop(self) -> None:
        if self._loop is None:
            return
        asyncio.set_event_loop(self._loop)

        async def start_server() -> Any:
            return await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                max_size=1024 * 1024,
                max_queue=32,
            )

        try:
            self._server = self._loop.run_until_complete(start_server())
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            self._loop.close()
            return
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _async_stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self.clients:
            await asyncio.gather(
                *(client.close() for client in self.clients),
                return_exceptions=True,
            )
            self.clients.clear()
        if self._loop is not None:
            self._loop.stop()

    async def _handle_client(self, websocket: Any) -> None:
        request = getattr(websocket, "request", None)
        headers = getattr(request, "headers", {})
        if headers.get("Origin", "") not in self.allowed_origins:
            await websocket.close(4005, "Origin not allowed")
            return
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            await websocket.close(4001, "Hello timeout: send hello within 5s")
            return
        except websockets.exceptions.ConnectionClosed:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.close(4002, "Invalid JSON")
            return
        if not isinstance(data, dict):
            await websocket.close(4002, "Invalid JSON object")
            return
        if data.get("event") != "hello":
            await websocket.close(4003, "First frame must be hello")
            return
        payload = data.get("payload")
        if (
            not isinstance(payload, dict)
            or payload.get("protocol") != GODOT_PROTOCOL_VERSION
            or payload.get("nonce") != self.handshake_nonce
        ):
            await websocket.close(4004, "Invalid Godot handshake")
            return
        await GodotProtocolV2Handler(
            session=self.runtime_session,
            clients=self.clients,
        ).handle(websocket, payload)

    @property
    def runtime_ready(self) -> bool:
        return self.runtime_session.ready_revision is not None

    @property
    def runtime_connection(self) -> RuntimeConnection | None:
        return self.runtime_session.active

    @property
    def runtime_world_revision(self) -> int | None:
        return self.runtime_session.ready_revision

    def send_runtime_command(
        self,
        name: CommandName,
        payload: JsonObject,
        *,
        world_revision: int,
        correlation_id: str | None = None,
    ) -> str | None:
        if self._loop is None or not self._loop.is_running():
            return None
        try:
            frame = self.runtime_session.create_command(
                name,
                payload,
                world_revision=world_revision,
                correlation_id=correlation_id,
            )
        except RuntimeSessionNotReadyError:
            return None
        asyncio.run_coroutine_threadsafe(
            self._broadcast(frame.model_dump(mode="json")),
            self._loop,
        )
        return frame.message_id

    def send_body_command(
        self,
        payload: RuntimeIntentPayload,
        *,
        correlation_id: str,
    ) -> bool:
        revision = self.runtime_session.ready_revision
        if revision is None:
            return False
        return (
            self.send_runtime_command(
                CommandName.EXECUTE_INTENT,
                cast(JsonObject, payload),
                world_revision=revision,
                correlation_id=correlation_id,
            )
            is not None
        )

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        revision = self.runtime_session.ready_revision
        if revision is None:
            return False
        return (
            self.send_runtime_command(
                CommandName.CANCEL_INTENT,
                {"command_id": command_id, "actor_id": actor_id},
                world_revision=revision,
                correlation_id=command_id,
            )
            is not None
        )

    def drain_runtime_events(self) -> tuple[RuntimeEventFrame, ...]:
        return self.runtime_session.drain_events()

    def mark_runtime_ready(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None:
        self.runtime_session.mark_ready(
            connection,
            world_revision=world_revision,
        )

    async def _broadcast(self, message: JsonObject) -> None:
        if not self.clients:
            return
        encoded = json.dumps(message, ensure_ascii=False)
        await asyncio.gather(
            *(client.send(encoded) for client in self.clients),
            return_exceptions=True,
        )


__all__ = ("GODOT_PROTOCOL_VERSION", "GodotAPIServer")
