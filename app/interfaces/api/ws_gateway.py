"""鉴权 WebSocket 网关 — token 验证 + 按 owner 过滤广播 + GodotAPI 共存。

``AuthenticatedWSManager`` 类管理 Web 管理面板的 WebSocket 连接，
监听独立端口 8766，不与 Godot 3D 客户端的 8765 端口冲突。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, Set

import websockets
import websockets.asyncio.server

from ai_runtime.storage.data_home import get_db_path as _get_db_path
from app.features.accounts import AccountsService
from app.interfaces.api.ws_gateway_messaging import WebSocketMessagingMixin
from app.interfaces.api.ws_gateway_session import WebSocketSessionMixin

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


class AuthenticatedWSManager(WebSocketSessionMixin, WebSocketMessagingMixin):
    """鉴权 WebSocket 网关，按 user_id 分组管理连接。

    与 GodotAPIServer（端口 8765）使用完全不同的协议层：
    - 连接建立后必须在 5 秒内发送 ``{"event":"auth"}``，会话从 HttpOnly cookie 读取
    - 验证通过后绑定 user_id，后续消息按 user_id 过滤
    - 提供 ``send_to_user`` / ``broadcast_to_owners`` 两个广播接口
    - 后台 asyncio 事件循环 + 线程模式（同 ``GodotAPIServer``）
    """

    def __init__(
        self,
        accounts: AccountsService,
        host: str = "127.0.0.1",
        port: int = 8766,
        http_port: int = 8000,
        db_path: str = None,
    ) -> None:
        self.host = host
        self.port = port
        self.http_port = http_port
        self.db_path = db_path if db_path is not None else str(_get_db_path())
        self.accounts = accounts

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
            error: Exception = TimeoutError("后台线程未在 3 秒内就绪")
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
