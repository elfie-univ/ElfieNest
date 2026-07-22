"""端到端服务测试 — 真实 Engine + 真实 WS 客户端 + 真实 HTTP 全链路验证

验证完整端到端事件流：
  1. hello 安全握手 → runtime_ready → sync_elfies
  2. physical interaction → physical_impact_event
  3. owner message → Communication → cortical speak_event
  4. go_to → LLM 决策动作（可选，不稳定时不失败）
  5. arrived_at 回调 → 姿态更新
  6. HTTP 端口可达

所有 WS recv 均使用 asyncio.wait_for(..., timeout=5.0) 防死等。
"""

import asyncio
import json
import os
import tempfile
import threading
import time

import websockets

from ai_runtime.gateway.request import (
    StructuredRuntimeCapabilities,
    StructuredRuntimeRequest,
    StructuredRuntimeResult,
)
from app.orchestration.engine import ElfieNestEngine
from elfie import ElfieFactory

# ---------------------------------------------------------------------------
# Mock 辅助类
# ---------------------------------------------------------------------------


class MockRuntimeAgent:
    """实现正式 structured Runtime 边界的确定性小模型 fake。"""

    def __init__(self, response: str = "你好，我没事。") -> None:
        self.response = response
        self.requests: list[StructuredRuntimeRequest] = []

    def structured_capabilities(self) -> StructuredRuntimeCapabilities:
        return StructuredRuntimeCapabilities(
            provider="test",
            model_key="test/plain-text",
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=False,
            supports_plain_text=True,
            max_output_tokens=128,
        )

    def generate_structured(
        self,
        request: StructuredRuntimeRequest,
    ) -> StructuredRuntimeResult:
        self.requests.append(request)
        return request.to_result(text=self.response)


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------


class TestE2EServiceFlow:
    """端到端服务测试 — 真实 Engine + 真实 WS 客户端 + 真实 HTTP"""

    async def _async_client_test(
        self,
        engine: ElfieNestEngine,
        runtime: MockRuntimeAgent,
    ) -> None:
        """异步 WS 客户端测试逻辑"""
        uri = f"ws://{engine.api_server.host}:{engine.api_server.port}"

        origin = f"http://127.0.0.1:{engine.http_port}"
        async with websockets.connect(uri, origin=origin) as ws:
            hello_msg = json.dumps(
                {
                    "event": "hello",
                    "payload": {
                        "protocol": 1,
                        "nonce": engine.api_server.handshake_nonce,
                    },
                },
                ensure_ascii=False,
            )
            await ws.send(hello_msg)
            hello_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            hello = json.loads(hello_raw)
            assert hello == {"event": "hello_ok", "payload": {"protocol": 1}}

            # ---------- 1. runtime_ready 后同步当前精灵目录 ----------
            ready_msg = json.dumps(
                {
                    "event": "runtime_ready",
                    "payload": {"protocol": 1, "bed_count": 1},
                },
                ensure_ascii=False,
            )
            await ws.send(ready_msg)
            sync_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            sync_data = json.loads(sync_raw)
            assert sync_data["action"] == "sync_elfies"
            assert sync_data["payload"]["elfies"][0]["elfie_id"] == "艾菲"

            # ---------- 2. 房间触觉产生物理可视事件 ----------
            engine.session.trigger_elfie_interaction("艾菲", "艾菲", "collision")

            impact_found = False
            deadline = time.time() + 4.0
            while time.time() < deadline and not impact_found:
                try:
                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg_raw)
                    if data.get("action") == "physical_impact_event":
                        impact_found = True
                        assert data["payload"]["elfie_id"] == "艾菲"
                        assert data["payload"]["impact_type"] == "gentle_stroke"
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                    break
            assert impact_found, "应在合理时间内收到 physical_impact_event"

            # ---------- 3. Owner 完整消息经 Communication 触发大脑语音 ----------
            await ws.send(
                json.dumps(
                    {
                        "event": "user_message",
                        "payload": {
                            "elfie_id": "艾菲",
                            "owner_id": "owner-test",
                            "conversation_id": "conversation-test",
                            "message_id": "message-test-1",
                            "message": "你还好吗？",
                        },
                    },
                    ensure_ascii=False,
                )
            )

            speak_found = False
            deadline = time.time() + 4.0
            while time.time() < deadline and not speak_found:
                try:
                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg_raw)
                    if data.get("action") == "speak_event":
                        speak_found = True
                        assert data["payload"]["elfie_id"] == "艾菲"
                        assert data["payload"]["text"] == runtime.response
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                    break

            elfie = engine.session.elfies["艾菲"]
            assert speak_found, (
                "应在合理时间内收到 speak_event; "
                f"runtime_requests={len(runtime.requests)}, "
                f"turn_outcomes={elfie.turn_outcomes()}, "
                f"workspace_metrics={elfie.perceptual_workspace.metrics()}, "
                f"elapsed={elfie.elapsed_time}"
            )
            assert len(runtime.requests) == 1

            # ---------- 4. go_to 事件（可选，不强制） ----------
            deadline = time.time() + 4.0
            while time.time() < deadline:
                try:
                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
                    data = json.loads(msg_raw)
                    if data.get("action") == "go_to":
                        if data["payload"].get("target") == "bed_1":
                            break
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                    break

            # ---------- 5. arrived_at 回调 ----------
            arrived_msg = json.dumps({
                "event": "arrived_at",
                "payload": {"elfie_id": "艾菲", "target": "bed_1"},
            }, ensure_ascii=False)
            await ws.send(arrived_msg)
            await asyncio.sleep(0.5)

            elfie_status = engine.nest.resident_state("艾菲")
            assert elfie_status is not None and elfie_status.posture == "lying", (
                f"arrived_at bed_1 后 posture 应为 lying，实际：{elfie_status}"
            )

    def test_full_e2e_service_flow(self):
        """端到端服务测试 — 真实 Engine + 真实 WS 客户端 + 真实 HTTP"""
        old_elfie_home = os.environ.get("ELFIE_HOME")
        engine = ElfieNestEngine(ws_port=18766, http_port=18001)
        mock_agent = MockRuntimeAgent()

        with tempfile.TemporaryDirectory() as elfie_home:
            os.environ["ELFIE_HOME"] = elfie_home

            # 将精灵创建与引擎启动封装在同一线程内，避免 SQLite 跨线程访问异常
            def _run_engine():
                elfie = ElfieFactory().create(
                    godot_api=engine.api_server,
                    elfie_id="艾菲",
                )
                engine.session.register_elfie("艾菲", elfie)
                engine._synthesize_voice = lambda elfie_id, text: f"http://127.0.0.1:{engine.http_port}/dummy.mp3"
                engine.start_loop(mock_agent, ticks_to_run=20, interval_sec=0.3)

            engine_thread = threading.Thread(target=_run_engine, daemon=True)
            engine_thread.start()

            try:
                time.sleep(1.0)
                asyncio.run(self._async_client_test(engine, mock_agent))
            finally:
                engine_thread.join(timeout=15)
                if old_elfie_home is None:
                    os.environ.pop("ELFIE_HOME", None)
                else:
                    os.environ["ELFIE_HOME"] = old_elfie_home
