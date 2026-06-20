import asyncio
import json
import logging
import threading
from collections.abc import Callable
from typing import Any, Dict, List, Set

import websockets
import websockets.asyncio.server

logger = logging.getLogger("elfienest.transport.godot_api")


class GodotAPIServer:
    """
    Godot WebSocket API 通信网关。
    采用"同步主线程 + 异步IO通信线程"的黄金架构设计。
    在独立的后台线程中运行 asyncio 事件循环，确保主游戏 Tick 循环绝对不被网络 IO 阻塞，
    同时提供线程安全的同步接口供外部调用。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port

        # 所有的活跃客户端连接
        self.clients: Set[Any] = set()

        # 事件回调映射表 { "event_name": [callback_fn] }
        self.event_callbacks: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

        # 后台通信线程与 asyncio 事件循环
        self._loop: Any = None
        self._thread: Any = None
        self._server: Any = None
        self._running = False

    def register_callback(
        self, event_name: str, callback: Callable[[Dict[str, Any]], None]
    ):
        """注册针对 Godot 事件的监听回调"""
        if event_name not in self.event_callbacks:
            self.event_callbacks[event_name] = []
        self.event_callbacks[event_name].append(callback)
        logger.info(f"🔌 [通信网关] 已成功注册事件 '{event_name}' 的监听回调")

    def start(self):
        """启动后台 WebSocket 服务端线程"""
        if self._running:
            return

        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_event_loop, daemon=True, name="ElfieNest_WS_Thread"
        )
        self._thread.start()

        # 等待事件循环在后台线程中就绪
        import time

        t0 = time.time()
        while self._loop is None or not self._loop.is_running():
            time.sleep(0.05)
            if time.time() - t0 > 3.0:
                logger.error("❌ [通信网关] 后台通信线程启动超时！")
                break
        logger.info(
            f"🚀 [通信网关] 后台通信线程就绪，正在 {self.host}:{self.port} 监听连接..."
        )

    def stop(self):
        """停止 WebSocket 服务器并清理资源"""
        if not self._running:
            return

        self._running = False
        if self._loop and self._loop.is_running():
            # 优雅在后台线程中关闭 Server 并停止 loop
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)

        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("🛑 [通信网关] 服务端已彻底关闭。")

    def _run_event_loop(self):
        """后台线程的执行体：启动 asyncio 事件循环并绑定 server"""
        asyncio.set_event_loop(self._loop)

        # 启动 WebSocket 服务器
        # websockets v16+ 中 serve 是类，__init__ 要求事件循环已运行，
        # 因此包装在 async 函数中通过 run_until_complete 启动，确保 await 时 loop 已运行
        async def _start_server():
            return await websockets.serve(self._handle_client, self.host, self.port)  # type: ignore[arg-type]

        self._server = self._loop.run_until_complete(_start_server())

        try:
            self._loop.run_forever()
        except Exception as e:
            logger.debug(f"[通信网关] 事件循环退出异常: {e}")
        finally:
            self._loop.close()

    async def _async_stop(self):
        """异步关闭连接和服务器协程"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # 强行关闭所有客户端连接
        if self.clients:
            close_tasks = [client.close() for client in self.clients]
            await asyncio.gather(*close_tasks, return_exceptions=True)
            self.clients.clear()

        self._loop.stop()

    async def _handle_client(self, websocket: Any):
        """处理来自 Godot 的新连接以及接收到的 JSON 消息"""
        logger.info(
            f"🤝 [通信网关] 收到来自 Godot 的连接握手: {websocket.remote_address}"
        )
        self.clients.add(websocket)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    event_name = data.get("event")
                    payload = data.get("payload", {})

                    if event_name:
                        logger.info(
                            f"📥 [通信网关] 接收到 Godot 事件: {event_name} - {payload}"
                        )
                        self._trigger_callbacks(event_name, payload)
                    else:
                        logger.warning(
                            f"⚠️ [通信网关] 收到无 event 标签的非法消息: {message}"
                        )
                except json.JSONDecodeError:
                    logger.error(f"❌ [通信网关] 消息解析 JSON 失败: {message}")
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(
                f"👋 [通信网关] Godot 连接断开: {websocket.remote_address} (code={e.code})"
            )
        finally:
            self.clients.discard(websocket)

    def _trigger_callbacks(self, event_name: str, payload: Dict[str, Any]):
        """在主/回调线程中触发注册的回调函数，带有防御性异常处理"""
        callbacks = self.event_callbacks.get(event_name, [])
        for cb in callbacks:
            try:
                cb(payload)
            except Exception as e:
                logger.error(
                    f"❌ [通信网关] 执行回调 '{cb.__name__}' 抛出异常: {e}",
                    exc_info=True,
                )

    def send_action(self, action: str, payload: Dict[str, Any]):
        """
        向所有已连接的 Godot 客户端发送语义命令（线程安全接口）。
        由同步主 Tick 线程调用，内部将其打包分发给 asyncio 后台线程。
        """
        if not self._running or not self._loop:
            logger.warning("⚠️ [通信网关] 服务未启动，发送命令取消。")
            return

        message_dict = {"action": action, "payload": payload}

        # 在 asyncio 线程安全地派发任务
        asyncio.run_coroutine_threadsafe(
            self._async_broadcast(message_dict), self._loop
        )

    async def _async_broadcast(self, message_dict: Dict[str, Any]):
        """异步广播消息给所有 Godot 客户端"""
        if not self.clients:
            logger.debug("⚠️ [通信网关] 暂无已连接的 Godot 客户端，指令已暂存入虚空。")
            return

        msg_str = json.dumps(message_dict, ensure_ascii=False)
        logger.info(f"📤 [通信网关] 发送语义命令 -> Godot: {msg_str}")

        send_tasks = [client.send(msg_str) for client in self.clients]
        await asyncio.gather(*send_tasks, return_exceptions=True)

    def send_expression(self, expression_data: dict):
        """发送情绪表达事件到Godot

        Args:
            expression_data: 表达参数，包含expression, actions, voice_modifier等
        """
        self.send_action("emotion_expression", expression_data)
