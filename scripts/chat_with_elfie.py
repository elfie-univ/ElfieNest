#!/usr/bin/env python3
"""ElfieNest 交互式聊天客户端

启动完整服务栈，让用户可以在终端里跟精灵 "艾菲" 对话。
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)-25s - %(levelname)-6s - %(message)s",
)
logger = logging.getLogger("chat")

from elfie import ElfieFactory
from app.orchestration.engine import ElfieNestEngine
from ai_runtime import LLMRuntimeConfig, RuntimeAgent


def main():
    # 使用线程内共享容器，让精灵和引擎在同一线程中创建，避免 SQLite 跨线程报错
    engine_holder: dict = {}
    engine_ready = threading.Event()

    def engine_worker():
        # 1. 装配服务（复刻 main.py 流程，全部在同一线程内完成）
        config = LLMRuntimeConfig(
            ollama_host="http://localhost:11434",
            ollama_model_fast="qwen3.5:0.8b",
        )
        runtime_agent = RuntimeAgent(config)
        engine = ElfieNestEngine()
        elfie = ElfieFactory().create(
            elfie_id="艾菲",
            godot_api=engine.api_server,
        )
        engine.session.register_elfie("艾菲", elfie)
        engine_holder["engine"] = engine
        engine_ready.set()
        # 2. 启动引擎主循环（阻塞）
        engine.start_loop(
            runtime_agent=runtime_agent, ticks_to_run=100000, interval_sec=3.0
        )

    engine_thread = threading.Thread(target=engine_worker, daemon=True)
    engine_thread.start()

    # 等待引擎线程把 engine 实例准备好
    engine_ready.wait(timeout=5.0)
    if "engine" not in engine_holder:
        print("❌ 引擎未能在 5 秒内就绪")
        sys.exit(1)
    engine = engine_holder["engine"]
    time.sleep(2.0)  # 等服务就绪

    # 3. 交互式循环
    print("=" * 60)
    print("🦊 ElfieNest 交互式聊天")
    print("输入消息跟艾菲聊天，输入 quit/exit/q 退出")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n👤 你说: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        # 发送消息给精灵
        engine.session.send_user_message("艾菲", user_input)
        print("⏳ 艾菲正在思考...")

    # 4. 清理
    engine.api_server.stop()
    engine.audio_server.stop()


if __name__ == "__main__":
    main()
