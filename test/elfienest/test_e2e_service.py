"""端到端服务测试 — 真实 Engine + 真实 WS 客户端 + 真实 HTTP 全链路验证

验证完整端到端事件流：
  1. register_scene 握手 → 家具注册
  2. physical_impact_event → 碰撞反射 WS 消息
  3. speak_event → 反射弧自动语音 WS 消息
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
import urllib.request

import websockets

from elfie import ElfieIndividual
from elfienest.simulation.engine import ElfieNestEngine

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
    """端到端服务测试 — 真实 Engine + 真实 WS 客户端 + 真实 HTTP"""

    async def _async_client_test(self, engine: ElfieNestEngine):
        """异步 WS 客户端测试逻辑"""
        uri = f"ws://{engine.api_server.host}:{engine.api_server.port}"

        async with websockets.connect(uri) as ws:
            # ---------- 1. register_scene 握手 ----------
            register_msg = json.dumps({
                "event": "register_scene",
                "payload": {"furniture": ["bed_1", "chair_1"]},
            }, ensure_ascii=False)
            await ws.send(register_msg)

            # 轮询等待 WS 服务端回调处理完成（跨线程，需要足够等待）
            furniture_registered = False
            for _ in range(30):
                await asyncio.sleep(0.1)
                furniture = engine.room.room_state.get("furniture", {})
                if "bed_1" in furniture and "chair_1" in furniture:
                    furniture_registered = True
                    break

            assert furniture_registered, (
                f"家具注册后应包含 bed_1 和 chair_1，实际：{list(engine.room.room_state.get('furniture', {}).keys())}"
            )

            # ---------- 2. physical_impact_event ----------
            engine.coordinator.trigger_elfie_interaction("艾菲", "艾菲", "collision")

            msg_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg_raw)
            assert data["action"] == "physical_impact_event", (
                f"第一条消息应为 physical_impact_event，实际：{data}"
            )
            assert data["payload"]["elfie_id"] == "艾菲"

            # ---------- 3. speak_event（反射弧自动语音） ----------
            speak_found = False
            deadline = time.time() + 4.0
            while time.time() < deadline:
                try:
                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg_raw)
                    if data.get("action") == "speak_event":
                        speak_found = True
                        assert data["payload"]["elfie_id"] == "艾菲"
                        assert data["payload"]["text"], (
                            f"speak_event 的 text 不应为空，实际：{data['payload']}"
                        )
                        break
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                    break

            assert speak_found, "应在合理时间内收到 speak_event"

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

            elfie_status = engine.room.room_state["elfies_status"].get("艾菲", {})
            assert elfie_status.get("posture") == "lying", (
                f"arrived_at bed_1 后 posture 应为 lying，实际：{elfie_status}"
            )

        # ---------- 6. HTTP 端口可达 ----------
        http_url = f"http://127.0.0.1:{engine.http_port}/"
        with urllib.request.urlopen(http_url, timeout=5.0) as resp:
            assert resp.status == 200, f"HTTP 服务应返回 200，实际：{resp.status}"

    def test_full_e2e_service_flow(self):
        """端到端服务测试 — 真实 Engine + 真实 WS 客户端 + 真实 HTTP"""
        old_elfie_home = os.environ.get("ELFIE_HOME")
        engine = ElfieNestEngine(ws_port=18766, http_port=18001)
        mock_agent = MockRuntimeAgent()

        with tempfile.TemporaryDirectory() as elfie_home:
            os.environ["ELFIE_HOME"] = elfie_home

            # 将精灵创建与引擎启动封装在同一线程内，避免 SQLite 跨线程访问异常
            def _run_engine():
                elfie = ElfieIndividual()
                engine.coordinator.register_elfie("艾菲", elfie)
                engine._synthesize_voice = lambda elfie_id, text: f"http://127.0.0.1:{engine.http_port}/dummy.mp3"
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
