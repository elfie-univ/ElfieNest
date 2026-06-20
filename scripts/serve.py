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


class FallbackAgent:
    """Ollama 不可用时的轻量模拟对话引擎"""

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

    def ask(self, prompt, energy=100, task_complexity=1):
        """返回模拟回复（毫秒级）"""
        import random

        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in ["你好", "嗨", "hello", "hi", "hey"]):
            return "你好呀！我是艾菲，一只可爱的小狐狸！今天想跟我聊什么呢？ [ACTION]wag_tail[/ACTION]"
        if any(kw in prompt_lower for kw in ["名字", "叫什么", "你是谁"]):
            return "我叫艾菲！是一只生活在 ElfieNest 里的小狐狸精灵。我有一身橙红色的毛皮，最喜欢主人摸我的尾巴啦！ [ACTION]wag_tail[/ACTION]"
        if any(kw in prompt_lower for kw in ["天气", "今天"]):
            return "唔...我这边天气挺好的！阳光透过窗户照进来，暖洋洋的。不过我没有窗户，只是感觉到的~ [ACTION]stretch[/ACTION]"
        if any(kw in prompt_lower for kw in ["开心", "高兴", "快乐"]):
            return "当然开心啦！主人来找我聊天，我就超开心的！ [ACTION]jump[/ACTION]"
        if any(kw in prompt_lower for kw in ["吃", "饿", "食物", "零食"]):
            return "吃的！我最喜欢小饼干和水果了！不过作为精灵，我好像不太需要吃东西...但是看到好吃的还是会馋！ [ACTION]lick_lips[/ACTION]"
        if any(kw in prompt_lower for kw in ["睡", "困", "晚安"]):
            return "哈欠~~~有点困了呢...但我还想再陪主人聊一会儿！ [ACTION]yawn[/ACTION]"
        if any(kw in prompt_lower for kw in ["再见", "拜拜", "bye", "quit", "exit"]):
            return "嗯！主人再见！随时来找我玩哦！ [ACTION]wave[/ACTION]"

        replies = [
            "嗯嗯，我在听呢！继续继续说~ [ACTION]listen[/ACTION]",
            "原来是这样啊！艾菲明白了！ [ACTION]nod_head[/ACTION]",
            "有意思！主人再多讲点嘛！ [ACTION]tilt_head[/ACTION]",
            "诶？这个我不太懂，但是我会努力去理解的！ [ACTION]think[/ACTION]",
            "好哒好哒！你说什么我都爱听！ [ACTION]wag_tail[/ACTION]",
        ]
        return random.choice(replies)


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

        runtime_agent = None
        try:
            import urllib.request

            resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
            if resp.status == 200:
                runtime_agent = RuntimeAgent(config)
        except Exception:
            pass

        if runtime_agent is None:
            runtime_agent = FallbackAgent()
            print("  ⚡ 使用内置对话引擎（Ollama 未运行）")
            print("  💡 如需真实 AI 回复，运行: ollama run qwen3.5:0.8b")
        else:
            print("  ✅ Ollama 已连接，使用真实 LLM")

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