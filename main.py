import logging
import sys

from ai_runtime import LLMRuntimeConfig, RuntimeAgent
from ai_runtime.storage.data_home import get_db_path, get_elfie_workspace_dir
from app.bootstrap.runtime_food import final_food_policy_loader
from app.infrastructure.persistence.store import init_db
from app.orchestration.engine import ElfieNestEngine
from elfie import ElfieFactory


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
    db_path = init_db(str(get_db_path()))
    runtime_agent = RuntimeAgent(
        config,
        live_reload=True,
        food_policy_loader=final_food_policy_loader(db_path),
    )
    logger.info("⚡ [底座算力底座就绪] 本地快速大模型及云端路由检测完毕。")

    # 2. 启动 ElfieNest 生态盒子游戏引擎
    engine = ElfieNestEngine()

    # 3. 唤醒精灵个体，并装配 Godot 中的 NativeBody
    elfie = ElfieFactory().create(
        config_dir=get_elfie_workspace_dir("00000001"),
        elfie_id="00000001",
        godot_api=engine.api_server,
    )
    logger.info(
        "✨ [灵魂注入完成] 艾菲 (Elfie) 的顶层认知、中层边缘化学、底层感觉神经融合完毕！"
    )

    # 4. 将艾菲注册到精灵盒子生态协调器中
    engine.session.register_elfie("00000001", elfie)

    # 5. 模拟一个物理碰撞，先逗一下小狐狸，刺激其情绪化学引擎发生变化
    logger.info("\n[世界物理交互] 模拟主人轻轻揉了揉艾菲的尾巴 (触发物理社交)...")
    engine.session.trigger_elfie_interaction(
        "00000001", "00000001", event_type="collision"
    )

    # 6. 开启世界物理 Tick 仿真循环
    # 运行 3 个 Tick 周期，周期 2 将自动触发主人的算术题微信提问，演示完整的防幻觉 Python 沙箱回调！
    logger.info(
        "\n======================== 🚀 启动物理盒子时间流动 ========================"
    )
    engine.start_loop(runtime_agent=runtime_agent, ticks_to_run=3, interval_sec=1.5)

    logger.info(
        "\n========================================================================="
    )
    logger.info("🎉 仿真结束！长期记忆写入 ELFIE_HOME 下的 knowledge.sqlite")
    logger.info(
        "========================================================================="
    )


if __name__ == "__main__":
    main()
