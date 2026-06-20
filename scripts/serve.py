#!/usr/bin/env python3
"""ElfieNest 后端服务 — 启动引擎，供浏览器聊天页面连接"""
import os
import sys
import threading
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 只显示 WARNING 以上日志，终端保持干净
logging.basicConfig(level=logging.WARNING, format="%(message)s")

from elfie import ElfieIndividual
from elfienest import ElfieNestEngine
from runtime import LLMRuntimeConfig, RuntimeAgent


def main():
    # 使用线程内共享容器，让精灵和引擎在同一线程中创建，避免 SQLite 跨线程报错
    engine_holder: dict = {}
    engine_ready = threading.Event()

    def engine_worker():
        # 1. 装配服务（全部在同一线程内完成）
        config = LLMRuntimeConfig(
            ollama_host="http://localhost:11434",
            ollama_model_fast="qwen3.5:0.8b",
        )
        runtime_agent = RuntimeAgent(config)
        elfie = ElfieIndividual()
        engine = ElfieNestEngine()
        engine.coordinator.register_elfie("艾菲", elfie)
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

    # 3. 打印引导信息
    print()
    print("=" * 56)
    print("  🦊 ElfieNest 仿生生命体服务")
    print("=" * 56)
    print("  🌐 HTTP:    http://127.0.0.1:8000")
    print("  🔌 WebSocket: ws://127.0.0.1:8765")
    print()
    print("  📖 浏览器打开: http://127.0.0.1:8000/chat.html")
    print("  ⌨️  Ctrl+C 停止服务")
    print("=" * 56)
    print()

    # 4. 保持进程存活
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
        engine.api_server.stop()
        if engine.httpd:
            engine.httpd.shutdown()
            engine.httpd.server_close()
        print("服务已关闭。")


if __name__ == "__main__":
    main()