"""Same-origin WebSocket fan-out for already-persisted product messages."""

from __future__ import annotations

import asyncio
from typing import Callable, Dict, Set

from fastapi import WebSocket

from app.orchestration.message_delivery import LiveConversationMessage


class SameOriginMessagePublisher:
    """Keep authenticated sockets scoped to one member and publish typed messages."""

    def __init__(self, session_is_current: Callable[[str, int], bool]) -> None:
        self._session_is_current = session_is_current
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._tokens: Dict[WebSocket, str] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        self._loop = asyncio.get_running_loop()
        self._connections.setdefault(user_id, set()).add(websocket)
        self._tokens[websocket] = websocket.cookies.get("session_token", "")

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        self._tokens.pop(websocket, None)
        if not sockets:
            del self._connections[user_id]

    def publish_message(self, message: LiveConversationMessage) -> None:
        loop = self._loop
        if (
            loop is None
            or loop.is_closed()
            or message.owner_user_id not in self._connections
        ):
            return
        asyncio.run_coroutine_threadsafe(self._send(message), loop)

    async def _send(self, live: LiveConversationMessage) -> None:
        sockets = tuple(self._connections.get(live.owner_user_id, set()))
        stale: list[WebSocket] = []
        payload = {
            "event": "message",
            "message": {
                "id": live.message.id,
                "elfie_id": live.message.elfie_id,
                "sender": live.message.sender,
                "text": live.message.text,
                "created_at": live.message.created_at,
            },
        }
        for socket in sockets:
            token = self._tokens.get(socket, "")
            if not token or not self._session_is_current(token, live.owner_user_id):
                await socket.close(code=4004, reason="Session revoked")
                stale.append(socket)
                continue
            try:
                await socket.send_json(payload)
            except RuntimeError:
                stale.append(socket)
        for socket in stale:
            await self.disconnect(live.owner_user_id, socket)


__all__ = ("SameOriginMessagePublisher",)
