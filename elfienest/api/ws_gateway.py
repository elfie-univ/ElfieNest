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
from typing import Any, Dict, Optional, Set

import websockets
import websockets.asyncio.server

from elfienest.accounts.auth import verify_session
from elfienest.persistence.chat_history import (
    ChatMessageInput,
    ChatSender,
    record_chat_message,
)
from elfienest.persistence.store import get_db
from runtime.storage.data_home import get_db_path as _get_db_path

logger = logging.getLogger("elfienest.api.ws_gateway")


class AuthenticatedWSManager:
    """鉴权 WebSocket 网关，按 user_id 分组管理连接。

    与 GodotAPIServer（端口 8765）使用完全不同的协议层：
    - 连接建立后必须在 5 秒内发送 ``{"event":"auth","payload":{"token":"..."}}``
    - 验证通过后绑定 user_id，后续消息按 user_id 过滤
    - 提供 ``send_to_user`` / ``broadcast_to_owners`` 两个广播接口
    - 后台 asyncio 事件循环 + 线程模式（同 ``GodotAPIServer``）
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8766,
        db_path: str = None,
    ) -> None:
        self.host = host
        self.port = port
        self.db_path = db_path if db_path is not None else str(_get_db_path())

        # user_id -> Set[websocket] 映射
        self.connections: Dict[int, Set[Any]] = {}
        # websocket -> {user_id, role} 反向表（含 role 用于管理员广播）
        self._user_info: Dict[Any, Dict[str, Any]] = {}

        # 后台异步组件
        self._loop: Any = None
        self._thread: Any = None
        self._server: Any = None
        self._running = False

        # 可选注入：Coordinator 引用，用于处理 user_message 事件
        self.coordinator: Any = None

    # -------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------

    def start(self) -> None:
        """在后台线程中启动 WebSocket 服务器。幂等。"""
        if self._running:
            return

        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_event_loop,
            daemon=True,
            name="ElfieNest_WS_8766",
        )
        self._thread.start()

        import time

        t0 = time.time()
        while self._loop is None or not self._loop.is_running():
            time.sleep(0.05)
            if time.time() - t0 > 3.0:
                logger.error("❌ WS gateway 后台线程启动超时！")
                break
        logger.info(
            "🚀 WS gateway 已启动 %s:%d", self.host, self.port
        )

    def stop(self) -> None:
        """停止 WebSocket 服务器并清理连接。幂等。"""
        if not self._running:
            return

        self._running = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)

        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info(
            "🛑 WS gateway 已停止。端口 %d 已释放。", self.port
        )

    def _run_event_loop(self) -> None:
        """后台线程执行体：创建事件循环并启动 WebSocket 服务器。"""
        asyncio.set_event_loop(self._loop)

        async def _start_server():
            return await websockets.serve(
                self._handle_client, self.host, self.port
            )

        self._server = self._loop.run_until_complete(_start_server())

        try:
            self._loop.run_forever()
        except Exception as e:
            logger.debug("WS gateway 事件循环退出: %s", e)
        finally:
            self._loop.close()

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
            close_tasks = [
                ws.close(1001, "Server shutting down") for ws in all_ws
            ]
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self.connections.clear()
        self._user_info.clear()
        self._loop.stop()

    # -------------------------------------------------------------------
    # 连接管理
    # -------------------------------------------------------------------

    def _add_connection(
        self, user_id: int, ws: Any, role: str = "user"
    ) -> None:
        """将已验证的 WebSocket 连接加入 user_id 分组。"""
        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(ws)
        self._user_info[ws] = {"user_id": user_id, "role": role}

    def _remove_connection(self, user_id: int, ws: Any) -> None:
        """从分组和反向表中移除连接。"""
        if user_id in self.connections:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                del self.connections[user_id]
        self._user_info.pop(ws, None)

    # -------------------------------------------------------------------
    # 客户端处理（asyncio 上下文）
    # -------------------------------------------------------------------

    async def _handle_client(self, websocket: Any) -> None:
        """处理 WebSocket 客户端的鉴权、消息接收与连接生命周期。"""
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

        if data.get("event") != "auth":
            await websocket.close(
                4003, "First frame must be {'event':'auth', ...}"
            )
            return

        token = (data.get("payload") or {}).get("token", "")
        user = verify_session(token, self.db_path)
        if user is None:
            await websocket.close(4004, "Invalid or expired token")
            return

        user_id = user["id"]
        role = user.get("role", "user")
        self._add_connection(user_id, websocket, role)

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
                try:
                    await self._handle_message(user_id, message)
                except Exception:
                    logger.exception("WS 消息处理异常")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._remove_connection(user_id, websocket)
            logger.debug("WS 连接已清理 (user_id=%d)", user_id)

    async def _handle_message(
        self, user_id: int, raw: str
    ) -> None:
        """处理单条 WebSocket 消息。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return  # 静默忽略非 JSON

        event = data.get("event")
        payload = data.get("payload", {}) or {}

        if event == "user_message":
            elfie_id = payload.get("elfie_id", "")
            message = payload.get("message", "")
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

            if self.coordinator is not None:
                self.coordinator.send_user_message(elfie_id, message)
                logger.info(
                    "WS 用户 %d -> 精灵 '%s' 消息已投递", user_id, elfie_id
                )
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

    def send_to_user(
        self, user_id: int, message_dict: Dict[str, Any]
    ) -> None:
        """向指定 user_id 的所有 WS 连接发送消息。"""
        if user_id not in self.connections:
            return
        msg_str = json.dumps(message_dict, ensure_ascii=False)
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(
                    self.connections[user_id].copy(), msg_str
                ),
                self._loop,
            )

    def broadcast_to_owners(
        self, elfie_id: str, message_dict: Dict[str, Any]
    ) -> None:
        """向精灵 owner + 所有管理员连接广播消息。"""
        owner_id = self._get_elfie_owner(elfie_id)
        if owner_id is None:
            return

        msg_str = json.dumps(message_dict, ensure_ascii=False)
        self._record_elfie_message(elfie_id, owner_id, message_dict)

        # 收集目标连接：owner + 所有管理员
        target: Set[Any] = set()
        if owner_id in self.connections:
            target.update(self.connections[owner_id])

        for ws, info in list(self._user_info.items()):
            if info.get("role") == "admin":
                target.add(ws)

        if not target:
            return

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(target, msg_str), self._loop
            )

    async def _async_send_to_set(
        self, targets: Set[Any], message_str: str
    ) -> None:
        """异步向一组 WebSocket 连接发送消息。"""
        if not targets:
            return
        tasks = [
            ws.send(message_str)
            for ws in targets
            if ws in self._user_info  # 确保连接仍有效
        ]
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
        if event != "speak_event" or not isinstance(payload, dict):
            return
        text = str(payload.get("text") or "").strip()
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
