"""Authenticated WebSocket handshake and connection lifecycle helpers."""

from __future__ import annotations

import asyncio
import json
import logging
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlparse

import websockets

from app.features.accounts import AccountsService

logger = logging.getLogger("app.interfaces.api.ws_gateway")


class WebSocketSessionMixin:
    """Keep browser-origin and session validation out of the gateway facade."""

    def _add_connection(
        self: Any, user_id: int, ws: Any, role: str = "user", token: str = ""
    ) -> None:
        """将已验证的 WebSocket 连接加入 user_id 分组。"""
        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(ws)
        self._user_info[ws] = {"user_id": user_id, "role": role, "token": token}

    def _remove_connection(self: Any, user_id: int, ws: Any) -> None:
        """从分组和反向表中移除连接。"""
        if user_id in self.connections:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                del self.connections[user_id]
        self._user_info.pop(ws, None)

    def _session_is_current(self: Any, token: str, user_id: int) -> bool:
        """确认已建立连接的会话仍存在，支持 Owner 恢复立即撤销旧会话。"""
        user = self._accounts().authenticate_session(token)
        if user is None or user.user_id != user_id:
            return False
        connection = next(
            (
                info
                for info in self._user_info.values()
                if info.get("user_id") == user_id and info.get("token") == token
            ),
            None,
        )
        return connection is None or connection.get("role") == user.role

    @staticmethod
    def _session_token_from_websocket(websocket: Any) -> str:
        """Read the HttpOnly session cookie from a WebSocket handshake."""
        request = getattr(websocket, "request", None)
        headers = getattr(request, "headers", {})
        cookie_header = headers.get("Cookie", "")
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        morsel = cookies.get("session_token")
        return morsel.value if morsel is not None else ""

    def _origin_is_allowed(self: Any, origin: str) -> bool:
        """Allow browser handshakes originating from the local console only."""
        if not origin:
            return False
        try:
            parsed = urlparse(origin)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and hostname
            in {
                "127.0.0.1",
                "localhost",
                "::1",
            }
            and port == self.http_port
            and not parsed.username
            and not parsed.password
            and parsed.path in {"", "/"}
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
        )

    async def _handle_client(self: Any, websocket: Any) -> None:
        """处理客户端鉴权、消息接收与连接生命周期。"""
        request = getattr(websocket, "request", None)
        headers = getattr(request, "headers", {})
        if not self._origin_is_allowed(headers.get("Origin", "")):
            await websocket.close(4005, "Origin not allowed")
            return
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            await websocket.close(4001, "Auth timeout: send auth frame within 5s")
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
        if data.get("event") != "auth":
            await websocket.close(4003, "First frame must be {'event':'auth', ...}")
            return

        token = self._session_token_from_websocket(websocket)
        user = self._accounts().authenticate_session(token)
        if user is None:
            await websocket.close(4004, "Invalid or expired token")
            return

        user_id = user.user_id
        role = user.role
        self._add_connection(user_id, websocket, role, token)
        await websocket.send(
            json.dumps(
                {
                    "event": "auth_ok",
                    "payload": {
                        "user_id": user_id,
                        "account_id": user.account_id,
                        "role": role,
                    },
                },
                ensure_ascii=False,
            )
        )
        logger.info(
            "WS 用户 '%s'(id=%d, role=%s) 鉴权成功",
            user.account_id,
            user_id,
            role,
        )

        try:
            async for message in websocket:
                if not self._session_is_current(token, user_id):
                    await websocket.close(4004, "Session revoked")
                    break
                try:
                    await self._handle_message(user, message)
                except Exception:
                    logger.exception("WS 消息处理异常")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._remove_connection(user_id, websocket)
            logger.debug("WS 连接已清理 (user_id=%d)", user_id)

    def _accounts(self: Any) -> AccountsService:
        service = getattr(self, "accounts", None)
        if not isinstance(service, AccountsService):
            raise RuntimeError("WebSocket gateway has no Accounts service")
        return service


__all__ = ("WebSocketSessionMixin",)
