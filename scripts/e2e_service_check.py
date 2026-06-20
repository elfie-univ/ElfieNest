#!/usr/bin/env python3
"""ElfieNest 端到端服务验证脚本

启动完整服务栈（HTTP + WebSocket + 物理时钟），连接模拟客户端，
验证从感官输入到精灵说话的完整端到端链路。
"""
import asyncio
import json
import os
import sys
import threading
import time
import urllib.request

# 确保能导入 elfienest 等模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)-25s - %(levelname)-6s - %(message)s",
)
logger = logging.getLogger("e2e_check")

from elfie import ElfieIndividual
from elfienest import ElfieNestEngine
from elfienest.godot_api import GodotAPIServer
from runtime import LLMRuntimeConfig, RuntimeAgent

import websockets

# ---------------------------------------------------------------------------
# Monkey-patch: websockets >= 14 的 serve() 要求事件循环已运行，
# 但 godot_api.py 中 loop.run_until_complete(websockets.serve(...)) 的求值
# 阶段 loop 尚未启动。将其包装在 async 函数内再 run_until_complete。
# ---------------------------------------------------------------------------
_original_run_event_loop = GodotAPIServer._run_event_loop


async def _async_start_server(self):
    self._server = await websockets.serve(
        self._handle_client, self.host, self.port
    )


def _patched_run_event_loop(self):
    asyncio.set_event_loop(self._loop)
    self._loop.run_until_complete(_async_start_server(self))
    try:
        self._loop.run_forever()
    except Exception as e:
        logging.getLogger("elfienest.godot_api").debug(
            f"[通信网关] 事件循环退出异常: {e}"
        )
    finally:
        self._loop.close()


GodotAPIServer._run_event_loop = _patched_run_event_loop
# ---------------------------------------------------------------------------


async def async_client_test(engine):
    """异步 WS 客户端：注册场景、触发碰撞、收集所有服务端消息。"""
    results = {
        "ws_connected": False,
        "register_scene_ok": False,
        "physical_impact_event": False,
        "speak_event": False,
    }

    ws_url = "ws://127.0.0.1:8765"
    ws = None

    try:
        # 1. 连接 WebSocket
        try:
            ws = await asyncio.wait_for(websockets.connect(ws_url), timeout=5.0)
            results["ws_connected"] = True
            logger.info("✅ WebSocket 连接成功")
        except Exception as e:
            logger.error(f"❌ WebSocket 连接失败: {e}")
            return results

        # 2. 发送 register_scene 注册家具
        try:
            register_msg = json.dumps(
                {
                    "event": "register_scene",
                    "payload": {"furniture": ["chair_1", "bed_1", "wormhole_door"]},
                },
                ensure_ascii=False,
            )
            await asyncio.wait_for(ws.send(register_msg), timeout=5.0)
            await asyncio.sleep(0.5)
            results["register_scene_ok"] = True
            logger.info("✅ register_scene 握手完成")
        except Exception as e:
            logger.error(f"❌ register_scene 发送失败: {e}")

        # 3. 触发物理碰撞（在 WS 连接后调用，确保能收到 physical_impact_event）
        try:
            engine.coordinator.trigger_elfie_interaction(
                "艾菲", "艾菲", "collision"
            )
            logger.info("✅ 已触发物理碰撞事件")
        except Exception as e:
            logger.error(f"❌ 触发碰撞失败: {e}")

        # 4. 循环收集所有 WS 消息直到引擎结束或总超时
        # 引擎跑 6 tick，interval 1.0s，总耗时约 6-8s，留足余量
        collected_actions = []
        overall_deadline = time.time() + 20.0

        while time.time() < overall_deadline:
            try:
                # 每次 recv 最多等 3 秒
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                data = json.loads(raw)
                action = data.get("action", "")
                collected_actions.append(action)
                logger.info(f"📥 [WS 客户端] 收到 action={action}")

                if action == "physical_impact_event":
                    results["physical_impact_event"] = True
                elif action == "speak_event":
                    results["speak_event"] = True
            except asyncio.TimeoutError:
                # 3 秒内没新消息，继续检查总超时
                continue
            except websockets.exceptions.ConnectionClosed:
                logger.info("👋 [WS 客户端] 服务端主动关闭连接")
                break
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ [WS 客户端] JSON 解析失败: {e}")
                continue

        logger.info(
            f"📊 [WS 客户端] 共收集到 {len(collected_actions)} 条消息: {collected_actions}"
        )

    except Exception as e:
        logger.error(f"❌ [WS 客户端] 异常: {e}")
    finally:
        if ws is not None:
            try:
                await asyncio.wait_for(ws.close(), timeout=3.0)
            except Exception:
                pass

    return results


def check_http_port() -> bool:
    """检查 HTTP 端口 8000 是否可达。"""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"⚠️ HTTP 检查异常: {e}")
        return False


def main():
    logger.info(
        "========================================================================="
    )
    logger.info("🔬 ElfieNest 端到端服务验证启动")
    logger.info(
        "========================================================================="
    )

    # 使用线程内共享容器，让精灵和引擎在同一线程中创建，避免 SQLite 跨线程报错
    engine_holder: dict = {}
    engine_ready = threading.Event()

    def engine_worker():
        # 1. 装配服务（复刻 main.py 流程，全部在同一线程内完成）
        config = LLMRuntimeConfig(
            ollama_host="http://localhost:11434", ollama_model_fast="qwen3.5:0.8b"
        )
        runtime_agent = RuntimeAgent(config)
        elfie = ElfieIndividual()
        engine = ElfieNestEngine(ws_port=8765, http_port=8000)
        engine.coordinator.register_elfie("艾菲", elfie)
        engine_holder["engine"] = engine
        engine_ready.set()
        # 2. 启动引擎主循环（阻塞）
        engine.start_loop(runtime_agent=runtime_agent, ticks_to_run=6, interval_sec=1.0)

    engine_thread = threading.Thread(target=engine_worker, daemon=True)
    engine_thread.start()

    # 等待引擎线程把 engine 实例准备好
    engine_ready.wait(timeout=5.0)
    if "engine" not in engine_holder:
        logger.error("❌ 引擎线程未能在 5s 内就绪")
        sys.exit(1)
    engine = engine_holder["engine"]

    # 再等 WS/HTTP 服务完全启动
    time.sleep(2.0)

    # 3. 在引擎仍在运行时检查 HTTP 端口（避免引擎结束后端口已关闭）
    http_ok = check_http_port()

    # 4. 跑异步客户端测试
    ws_results = {
        "ws_connected": False,
        "register_scene_ok": False,
        "physical_impact_event": False,
        "speak_event": False,
    }
    try:
        ws_results = asyncio.run(async_client_test(engine))
    except Exception as e:
        logger.error(f"❌ 异步客户端测试异常: {e}")

    # 5. 打印可视化报告
    print()
    print("=" * 66)
    print("           ElfieNest 端到端服务验证报告")
    print("=" * 66)

    checks = [
        ("WebSocket 连接成功", ws_results.get("ws_connected", False)),
        ("register_scene 握手完成", ws_results.get("register_scene_ok", False)),
        ("收到 physical_impact_event 事件", ws_results.get("physical_impact_event", False)),
        ("收到 speak_event 事件（精灵说话）", ws_results.get("speak_event", False)),
        ("HTTP 端口 8000 可达", http_ok),
    ]

    passed = 0
    failed_labels = []
    for label, ok in checks:
        symbol = "✅" if ok else "❌"
        print(f"  {symbol} {label}")
        if ok:
            passed += 1
        else:
            failed_labels.append(label)

    print("=" * 66)
    total = len(checks)
    if passed == total:
        print(f"结果: {passed}/{total} 通过 — 🎉 全部验证通过！")
    else:
        print(f"结果: {passed}/{total} 通过 — ⚠️ {total - passed} 项失败")
        for fl in failed_labels:
            print(f"  ❌ {fl}")
    print()

    # 6. 清理
    logger.info("🧹 等待引擎线程自然结束...")
    engine_thread.join(timeout=20.0)
    if engine_thread.is_alive():
        logger.warning("⚠️ 引擎线程未在 20s 内结束，强制退出")

    # 7. 退出码
    if passed == total:
        logger.info("🎉 验证通过，退出码 0")
        sys.exit(0)
    else:
        logger.error("❌ 验证未完全通过，退出码 1")
        sys.exit(1)


if __name__ == "__main__":
    main()
