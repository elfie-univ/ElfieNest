"""Same-origin delivery of persisted Elfie replies to product chat clients."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Set

from fastapi import WebSocket

from app.infrastructure.persistence.chat_history import (
    ChatHistoryQuery,
    list_chat_history,
)
from app.infrastructure.persistence.store import get_db


class SameOriginChatHub:
    """Fan out an already-persisted reply only to the owning user's sockets."""

    def __init__(self, db_path: str) -> None:
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._db_path = db_path
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """Remember a socket after its HTTP-session authentication succeeded."""
        self._loop = asyncio.get_running_loop()
        self._connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Forget a closed socket without affecting other tabs for the same user."""
        sockets = self._connections.get(user_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del self._connections[user_id]

    def publish_elfie_reply(self, elfie_id: str) -> None:
        """Send the latest persisted Elfie message to the owning user's open tabs."""
        owner_id = self._owner_id(elfie_id)
        if owner_id is None:
            return
        history = list_chat_history(self._db_path, ChatHistoryQuery(elfie_id, owner_id))
        latest = next((message for message in reversed(history) if message.sender == "elfie"), None)
        if latest is None:
            return
        self.publish_message(
            owner_id,
            {
                "id": latest.id,
                "elfie_id": latest.elfie_id,
                "sender": latest.sender,
                "text": latest.text,
                "created_at": latest.created_at,
            },
        )

    def publish_message(self, user_id: int, message: Dict[str, Any]) -> None:
        """Schedule a typed product-chat event on the loop that owns the sockets."""
        loop = self._loop
        if loop is None or loop.is_closed() or user_id not in self._connections:
            return
        asyncio.run_coroutine_threadsafe(self._send(user_id, message), loop)

    async def _send(self, user_id: int, message: Dict[str, Any]) -> None:
        sockets = tuple(self._connections.get(user_id, set()))
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json({"event": "message", "message": message})
            except RuntimeError:
                stale.append(socket)
        for socket in stale:
            await self.disconnect(user_id, socket)

    def _owner_id(self, elfie_id: str) -> int | None:
        with get_db(self._db_path) as connection:
            row = connection.execute(
                "SELECT owner_user_id FROM elfie_registry WHERE elfie_id = ?", (elfie_id,)
            ).fetchone()
        return int(row["owner_user_id"]) if row is not None else None
