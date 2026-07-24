"""鉴权 WebSocket 网关 — token 验证 + 按 owner 过滤广播 + GodotAPI 共存。

``AuthenticatedWSManager`` 类管理 Web 管理面板的 WebSocket 连接，
监听独立端口 8766，不与 Godot 3D 客户端的 8765 端口冲突。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from http.cookies import SimpleCookie
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

import websockets
import websockets.asyncio.server

from ai_runtime.storage.data_home import get_db_path as _get_db_path
from app.features.accounts.auth import verify_session
from app.infrastructure.persistence.chat_history import (
    ChatMessageInput,
    ChatSender,
    record_chat_message,
)
from app.infrastructure.persistence.store import get_db

logger = logging.getLogger("app.interfaces.api.ws_gateway")


class WebSocketGatewayStartError(RuntimeError):
    """WebSocket 网关无法在后台线程完成监听时抛出的启动错误。"""

    def __init__(self, host: str, port: int, reason: str) -> None:
        self.host = host
        self.port = port
        self.reason = reason
        super().__init__(self.__str__())

    def __str__(self) -> str:
        return f"WebSocket 网关启动失败 ({self.host}:{self.port}): {self.reason}"


class AuthenticatedWSManager:
    """鉴权 WebSocket 网关，按 user_id 分组管理连接。

    与 GodotAPIServer（端口 8765）使用完全不同的协议层：
    - 连接建立后必须在 5 秒内发送 ``{"event":"auth"}``，会话从 HttpOnly cookie 读取
    - 验证通过后绑定 user_id，后续消息按 user_id 过滤
    - 提供 ``send_to_user`` / ``broadcast_to_owners`` 两个广播接口
    - 后台 asyncio 事件循环 + 线程模式（同 ``GodotAPIServer``）
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8766,
        http_port: int = 8000,
        db_path: str = None,
    ) -> None:
        self.host = host
        self.port = port
        self.http_port = http_port
        self.db_path = db_path if db_path is not None else str(_get_db_path())

        # user_id -> Set[websocket] 映射
        self.connections: Dict[int, Set[Any]] = {}
        # websocket -> {user_id, role} 反向表（含 role 用于Owner广播）
        self._user_info: Dict[Any, Dict[str, Any]] = {}

        # 后台异步组件
        self._loop: Any = None
        self._thread: Any = None
        self._server: Any = None
        self._running = False
        self._startup_event = threading.Event()
        self._startup_error: Exception | None = None

        # 可选注入：NestSession 引用，用于处理 user_message 事件
        self.nest_session: Any = None
        # 新产品页的同源 WebSocket 桥；旧独立端口仍保持兼容。
        self.product_chat_hub: Any = None

    # -------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------

    def start(self) -> None:
        """在后台线程中启动 WebSocket 服务器。幂等。"""
        if self._running:
            return

        self._startup_event = threading.Event()
        self._startup_error = None
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_event_loop,
            daemon=True,
            name="ElfieNest_WS_8766",
        )
        self._thread.start()

        if not self._startup_event.wait(timeout=3.0):
            self._running = False
            self._request_loop_stop()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            error = TimeoutError("后台线程未在 3 秒内就绪")
            raise WebSocketGatewayStartError(
                self.host, self.port, str(error)
            ) from error

        if self._startup_error is not None:
            self._running = False
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            error = self._startup_error
            raise WebSocketGatewayStartError(
                self.host, self.port, str(error)
            ) from error

        if self._server is None or self._thread is None or not self._thread.is_alive():
            self._running = False
            error = RuntimeError("后台线程未保持运行")
            raise WebSocketGatewayStartError(
                self.host, self.port, str(error)
            ) from error

        logger.info("🚀 WS gateway 已启动 %s:%d", self.host, self.port)

    def stop(self) -> None:
        """停止 WebSocket 服务器并清理连接。幂等。"""
        if not self._running:
            return

        self._running = False
        loop = self._loop
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._async_stop(), loop)
            try:
                future.result(timeout=2.0)
            except (TimeoutError, RuntimeError) as exc:
                logger.debug("WS gateway 异步关闭未完成: %s", exc)
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)

        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("🛑 WS gateway 已停止。端口 %d 已释放。", self.port)

    def _run_event_loop(self) -> None:
        """后台线程执行体：创建事件循环并启动 WebSocket 服务器。"""
        loop = self._loop
        if loop is None:
            self._startup_error = RuntimeError("事件循环未创建")
            self._startup_event.set()
            return
        asyncio.set_event_loop(loop)

        async def _start_server():
            return await websockets.serve(self._handle_client, self.host, self.port)

        try:
            self._server = loop.run_until_complete(_start_server())
            if self.port == 0 and self._server.sockets:
                socket_name = self._server.sockets[0].getsockname()
                if isinstance(socket_name, tuple) and len(socket_name) >= 2:
                    self.port = int(socket_name[1])
            self._startup_event.set()
            loop.run_forever()
        except Exception as exc:
            self._startup_error = exc
            self._startup_event.set()
            logger.exception("WS gateway 事件循环启动失败: %s", exc)
        finally:
            self._startup_event.set()
            if self._server is not None:
                self._server.close()
            loop.close()

    def _request_loop_stop(self) -> None:
        """请求后台事件循环停止，覆盖启动阶段和正常运行阶段。"""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)

    async def _async_stop(self) -> None:
        """异步关闭服务器和所有连接。"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # 关闭所有活跃连接
        all_ws: Set[Any] = set()
        for ws_set in self.connections.values():
            all_ws.update(ws_set)
        if all_ws:
            close_tasks = [ws.close(1001, "Server shutting down") for ws in all_ws]
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self.connections.clear()
        self._user_info.clear()

    # -------------------------------------------------------------------
    # 连接管理
    # -------------------------------------------------------------------

    def _add_connection(
        self, user_id: int, ws: Any, role: str = "user", token: str = ""
    ) -> None:
        """将已验证的 WebSocket 连接加入 user_id 分组。"""
        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(ws)
        self._user_info[ws] = {"user_id": user_id, "role": role, "token": token}

    def _remove_connection(self, user_id: int, ws: Any) -> None:
        """从分组和反向表中移除连接。"""
        if user_id in self.connections:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                del self.connections[user_id]
        self._user_info.pop(ws, None)

    def _session_is_current(self, token: str, user_id: int) -> bool:
        """确认已建立连接的会话仍存在，支持本机 Owner 恢复立即撤销旧会话。"""
        user = verify_session(token, self.db_path)
        if user is None or user.get("id") != user_id:
            return False
        connection = next(
            (
                info
                for info in self._user_info.values()
                if info.get("user_id") == user_id and info.get("token") == token
            ),
            None,
        )
        return connection is None or connection.get("role") == user.get("role")

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

    def _origin_is_allowed(self, origin: str) -> bool:
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

    # -------------------------------------------------------------------
    # 客户端处理（asyncio 上下文）
    # -------------------------------------------------------------------

    async def _handle_client(self, websocket: Any) -> None:
        """处理 WebSocket 客户端的鉴权、消息接收与连接生命周期。"""
        request = getattr(websocket, "request", None)
        headers = getattr(request, "headers", {})
        if not self._origin_is_allowed(headers.get("Origin", "")):
            await websocket.close(4005, "Origin not allowed")
            return
        # ---- Step 1: 鉴权（5 秒超时） ----
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
        user = verify_session(token, self.db_path)
        if user is None:
            await websocket.close(4004, "Invalid or expired token")
            return

        user_id = user["id"]
        role = user.get("role", "user")
        self._add_connection(user_id, websocket, role, token)

        # 发送鉴权成功确认
        await websocket.send(
            json.dumps(
                {
                    "event": "auth_ok",
                    "payload": {
                        "user_id": user_id,
                        "username": user.get("username", ""),
                        "role": role,
                    },
                },
                ensure_ascii=False,
            )
        )

        logger.info(
            "WS 用户 '%s'(id=%d, role=%s) 鉴权成功",
            user.get("username", "?"),
            user_id,
            role,
        )

        # ---- Step 2: 消息循环 ----
        try:
            async for message in websocket:
                if not self._session_is_current(token, user_id):
                    await websocket.close(4004, "Session revoked")
                    break
                try:
                    await self._handle_message(user_id, message)
                except Exception:
                    logger.exception("WS 消息处理异常")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._remove_connection(user_id, websocket)
            logger.debug("WS 连接已清理 (user_id=%d)", user_id)

    async def _handle_message(self, user_id: int, raw: str) -> None:
        """处理单条 WebSocket 消息。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return  # 静默忽略非 JSON
        if not isinstance(data, dict):
            return

        event = data.get("event")
        payload = data.get("payload", {}) or {}
        if not isinstance(payload, dict):
            return

        if event == "user_message":
            elfie_id = payload.get("elfie_id")
            message = payload.get("message")
            if not isinstance(elfie_id, str) or not isinstance(message, str):
                return
            elfie_id = elfie_id.strip()
            message = message.strip()
            if not elfie_id or not message:
                return

            # 校验该精灵属于该用户
            if not self._is_elfie_owned_by(elfie_id, user_id):
                logger.warning(
                    "用户 %d 尝试给不属于他的精灵 '%s' 发消息，已拒绝",
                    user_id,
                    elfie_id,
                )
                return

            if self.nest_session is not None:
                self.nest_session.send_user_message(
                    elfie_id,
                    message,
                    owner_id=str(user_id),
                    conversation_id=str(
                        payload.get("conversation_id") or f"owner:{user_id}"
                    ),
                    external_message_id=(
                        str(payload["message_id"])
                        if payload.get("message_id") is not None
                        else None
                    ),
                    account_id=str(payload.get("account_id") or "owner-ws"),
                )
                logger.info("WS 用户 %d -> 精灵 '%s' 消息已投递", user_id, elfie_id)
            self._record_user_message(elfie_id, user_id, message)

    # -------------------------------------------------------------------
    # 数据库查询
    # -------------------------------------------------------------------

    def _is_elfie_owned_by(self, elfie_id: str, user_id: int) -> bool:
        """检查 elfie_id 是否属于 user_id。"""
        with get_db(self.db_path) as db:
            cursor = db.execute(
                "SELECT owner_user_id FROM elfie_registry WHERE elfie_id = ?",
                (elfie_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return False
            return row["owner_user_id"] == user_id

    def _get_elfie_owner(self, elfie_id: str) -> Optional[int]:
        """查询精灵的 owner_user_id。"""
        with get_db(self.db_path) as db:
            cursor = db.execute(
                "SELECT owner_user_id FROM elfie_registry WHERE elfie_id = ?",
                (elfie_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return row["owner_user_id"]

    # -------------------------------------------------------------------
    # 对外广播接口（线程安全，主线程调用）
    # -------------------------------------------------------------------

    def send_to_user(self, user_id: int, message_dict: Dict[str, Any]) -> None:
        """向指定 user_id 的所有 WS 连接发送消息。"""
        if user_id not in self.connections:
            return
        msg_str = json.dumps(message_dict, ensure_ascii=False)
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(self.connections[user_id].copy(), msg_str),
                self._loop,
            )

    def broadcast_to_owners(self, elfie_id: str, message_dict: Dict[str, Any]) -> None:
        """只向精灵所属用户的连接广播消息。"""
        owner_id = self._get_elfie_owner(elfie_id)
        if owner_id is None:
            return

        msg_str = json.dumps(message_dict, ensure_ascii=False)
        self._record_elfie_message(elfie_id, owner_id, message_dict)
        if self.product_chat_hub is not None:
            self.product_chat_hub.publish_elfie_reply(elfie_id)

        # 聊天与语音内容属于精灵所属用户，Owner/兼容Owner不能跨用户读取。
        target: Set[Any] = set()
        if owner_id in self.connections:
            target.update(self.connections[owner_id])

        if not target:
            return

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(target, msg_str), self._loop
            )

    async def _async_send_to_set(self, targets: Set[Any], message_str: str) -> None:
        """异步向一组 WebSocket 连接发送消息。"""
        if not targets:
            return
        valid_targets: list[Any] = []
        revoked_targets: list[Any] = []
        for ws in targets:
            info = self._user_info.get(ws)
            if info is None:
                continue
            token = info.get("token", "")
            user_id = info.get("user_id")
            if (
                isinstance(token, str)
                and isinstance(user_id, int)
                and self._session_is_current(token, user_id)
            ):
                valid_targets.append(ws)
            else:
                revoked_targets.append(ws)
        if revoked_targets:
            await asyncio.gather(
                *(ws.close(4004, "Session revoked") for ws in revoked_targets),
                return_exceptions=True,
            )
            for ws in revoked_targets:
                info = self._user_info.get(ws)
                if info is not None and isinstance(info.get("user_id"), int):
                    self._remove_connection(info["user_id"], ws)
        tasks = [ws.send(message_str) for ws in valid_targets if ws in self._user_info]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _record_user_message(self, elfie_id: str, user_id: int, message: str) -> None:
        try:
            record_chat_message(
                self.db_path,
                ChatMessageInput(
                    elfie_id=elfie_id,
                    user_id=user_id,
                    sender=ChatSender.USER,
                    text=message,
                    meta="已投递到下一次 tick",
                ),
            )
        except sqlite3.Error as exc:
            logger.warning("用户聊天消息持久化失败: %s", exc)

    def _record_elfie_message(
        self,
        elfie_id: str,
        user_id: int,
        message_dict: Dict[str, Any],
    ) -> None:
        event = message_dict.get("event") or message_dict.get("action")
        payload = message_dict.get("payload") or {}
        if not isinstance(payload, dict):
            return
        text = self._elfie_message_text(str(event), payload)
        if not text:
            return
        emotion = str(payload.get("emotion") or "").strip()
        try:
            record_chat_message(
                self.db_path,
                ChatMessageInput(
                    elfie_id=elfie_id,
                    user_id=user_id,
                    sender=ChatSender.ELFIE,
                    text=text,
                    meta=f"情绪：{emotion}" if emotion else "实时回复",
                ),
            )
        except sqlite3.Error as exc:
            logger.warning("精灵聊天消息持久化失败: %s", exc)

    @staticmethod
    def _elfie_message_text(event: str, payload: Dict[str, Any]) -> str:
        if event == "speak_event":
            return str(payload.get("text") or "").strip()
        if event != "owner_message":
            return ""
        parts = payload.get("parts") or []
        if not isinstance(parts, list):
            return ""
        texts = [
            str(part.get("text") or "").strip()
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(text for text in texts if text)
