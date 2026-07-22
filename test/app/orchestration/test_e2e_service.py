"""端到端服务测试 — 真实 Engine + 真实 WS 客户端全链路验证

验证完整端到端事件流：
  1. hello 安全握手 → runtime_ready → sync_elfies
  2. physical interaction → speak_event + emotion_expression
  4. go_to → LLM 决策动作（可选，不稳定时不失败）
  5. arrived_at 回调 → 姿态更新

所有 WS recv 均使用 asyncio.wait_for(..., timeout=5.0) 防死等。
"""

import asyncio
import json
import os
import tempfile
import threading
import time

import websockets

from elfie import ElfieFactory
from app.orchestration.engine import ElfieNestEngine

# ---------------------------------------------------------------------------
# Mock 辅助类
# ---------------------------------------------------------------------------


class MockRuntimeAgent:
    """模拟 LLM 运行时代理，记录所有调用供验证"""

    class MockConfig:
        remote_api_key = ""
        providers = {
            "deepseek": {"api_key": "", "api_base": ""},
            "openai": {"api_key": "", "api_base": ""},
            "gemini": {"api_key": "", "api_base": ""},
            "qwen": {"api_key": "", "api_base": ""},
            "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
        }

    config = MockConfig()

    def __init__(self, response="你好！ [ACTION]sleep[/ACTION]"):
        self.response = response
        self.ask_calls = []

    def ask(self, prompt, energy, task_complexity):
        self.ask_calls.append({
            "prompt": prompt,
            "energy": energy,
            "complexity": task_complexity,
        })
        return self.response


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------


class TestE2EServiceFlow:
    """端到端服务测试 — 真实 Engine + 真实 WS 客户端。"""

    async def _async_client_test(self, engine: ElfieNestEngine):
        """异步 WS 客户端测试逻辑"""
        uri = f"ws://{engine.api_server.host}:{engine.api_server.port}"

        origin = "http://127.0.0.1:18001"
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

            # ---------- 2. 触觉反射通过 NativeBody 发出语音与表情 ----------
            engine.session.trigger_elfie_interaction("艾菲", "艾菲", "collision")

            speak_found = False
            expression_found = False
            deadline = time.time() + 4.0
            while time.time() < deadline and not (speak_found and expression_found):
                try:
                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg_raw)
                    if data.get("action") == "speak_event":
                        speak_found = True
                        assert data["payload"]["elfie_id"] == "艾菲"
                        assert data["payload"]["text"], (
                            f"speak_event 的 text 不应为空，实际：{data['payload']}"
                        )
                    elif data.get("action") == "emotion_expression":
                        expression_found = True
                        assert data["payload"]["elfie_id"] == "艾菲"
                        assert "reflex_soothing" in data["payload"]["actions"]
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                    break

            assert speak_found, "应在合理时间内收到 speak_event"
            assert expression_found, "应在合理时间内收到 emotion_expression"

            # ---------- 3. go_to 事件（可选，不强制） ----------
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

            # ---------- 4. arrived_at 回调 ----------
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
        """端到端服务测试 — 真实 Engine + 真实 WS 客户端。"""
        old_elfie_home = os.environ.get("ELFIE_HOME")
        engine = ElfieNestEngine(ws_port=18766, godot_origin_port=18001)
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
                engine.start_loop(mock_agent, ticks_to_run=20, interval_sec=0.3)

            engine_thread = threading.Thread(target=_run_engine, daemon=True)
            engine_thread.start()

            try:
                time.sleep(1.0)
                asyncio.run(self._async_client_test(engine))
            finally:
                engine_thread.join(timeout=15)
                if old_elfie_home is None:
                    os.environ.pop("ELFIE_HOME", None)
                else:
                    os.environ["ELFIE_HOME"] = old_elfie_home
