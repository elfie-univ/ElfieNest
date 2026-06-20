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
    # 1. 装配
    config = LLMRuntimeConfig(
        ollama_host="http://localhost:11434",
        ollama_model_fast="qwen3.5:0.8b",
    )
    runtime_agent = RuntimeAgent(config)
    elfie = ElfieIndividual()
    engine = ElfieNestEngine()
    engine.coordinator.register_elfie("艾菲", elfie)

    # 2. 后台启动引擎
    thread = threading.Thread(
        target=engine.start_loop,
        args=(runtime_agent,),
        kwargs={"ticks_to_run": 100000, "interval_sec": 3.0},
        daemon=True,
    )
    thread.start()

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