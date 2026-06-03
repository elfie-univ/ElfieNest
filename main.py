import logging
import sys

from elfie import ElfieIndividual
from elfienest import ElfieNestEngine
from runtime import LLMRuntimeConfig, RuntimeAgent


def setup_logging():
    """配置精美的日志打印系统"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)-30s - %(levelname)-8s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # 调低一些吵闹模块的日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main():
    setup_logging()
    logger = logging.getLogger("main")

    logger.info(
        "========================================================================="
    )
    logger.info("🦊 唤醒仪式：正在读取大脑皮层及算力底座驱动，唤醒仿生生命体 Elfie...")
    logger.info(
        "========================================================================="
    )

    # 1. 启动外包大模型算力底座 (Runtime)
    # 本地未跑 Ollama 时会优雅自动降级到底座内建的“轻量模拟器”，100% 可完美体验三层大脑！
    config = LLMRuntimeConfig(
        ollama_host="http://localhost:11434", ollama_model_fast="qwen3.5:0.8b"
    )
    runtime_agent = RuntimeAgent(config)
    logger.info("⚡ [底座算力底座就绪] 本地快速大模型及云端路由检测完毕。")

    # 2. 唤醒精灵个体，为其注入专属灵魂 (Elfie 三层大脑)
    elfie = ElfieIndividual()
    logger.info(
        "✨ [灵魂注入完成] 艾菲 (Elfie) 的顶层认知、中层边缘化学、底层感觉神经融合完毕！"
    )

    # 3. 启动 ElfieNest 生态盒子游戏引擎
    engine = ElfieNestEngine()

    # 4. 将艾菲注册到精灵盒子生态协调器中
    engine.coordinator.register_elfie("艾菲", elfie)

    # 5. 模拟一个物理碰撞，先逗一下小狐狸，刺激其情绪化学引擎发生变化
    logger.info("\n[世界物理交互] 模拟主人轻轻揉了揉艾菲的尾巴 (触发物理社交)...")
    engine.coordinator.trigger_elfie_interaction("艾菲", "艾菲", event_type="collision")

    # 6. 开启世界物理 Tick 仿真循环
    # 运行 3 个 Tick 周期，周期 2 将自动触发主人的算术题微信提问，演示完整的防幻觉 Python 沙箱回调！
    logger.info(
        "\n======================== 🚀 启动物理盒子时间流动 ========================"
    )
    engine.start_loop(runtime_agent=runtime_agent, ticks_to_run=3, interval_sec=1.5)

    logger.info(
        "\n========================================================================="
    )
    logger.info("🎉 仿真结束！艾菲的历史海马体记忆已落盘至根目录 .elfie_memories.json")
    logger.info(
        "========================================================================="
    )


if __name__ == "__main__":
    main()
