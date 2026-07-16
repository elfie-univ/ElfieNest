#!/usr/bin/env python3
"""ElfieNest 后端服务 — FastAPI + 引擎后台线程共存 + DB 驱动动态精灵加载。

启动流程:
    1. 初始化 DB + seed admin 账号
    2. 可选项: 为 admin seed 初始精灵"艾菲" (--seed-elfie，默认开启)
    3. 引擎后台线程: RuntimeAgent → ElfieNestEngine (不硬编码精灵)
    4. 从 DB 查询 elfie_registry → 实例化 ElfieIndividual → 注册到引擎
    5. 创建 FastAPI app → uvicorn 阻塞主线程

命令行参数:
    --fallback      使用内置对话引擎（不连 Ollama）
    --port          HTTP 端口（默认 8000）
    --ws-port       鉴权 WebSocket 端口（默认 8766）
    --no-seed-elfie 不自动 seed 初始精灵
    --force         强制重启（杀死占用端口的进程）

CLI 工具:
    .venv/bin/python scripts/elfienest.py config    打开配置 TUI
    .venv/bin/python scripts/elfienest.py models    列出可用模型
    .venv/bin/python scripts/elfienest.py providers 管理 providers
    .venv/bin/python scripts/elfienest.py status    查看服务状态
    .venv/bin/python scripts/elfienest.py setup     首次设置向导
    .venv/bin/python scripts/elfienest.py restart   重启服务
    .venv/bin/python scripts/elfienest.py stop      停止服务
"""

import argparse
import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from elfienest.adoption.generator import ElfieGenerator
from elfienest.api.app import create_app
from elfienest.operations.godot_web import inspect_godot_web_bundle
from elfienest.operations.recovery_lock import (
    MANAGED_START_ENV,
    RecoveryInProgressError,
    acquire_service_start_lease,
)
from elfienest.operations.service_process import register_current_service
from elfienest.persistence.store import (
    get_db,
    init_db,
    migrate_db_if_needed,
    seed_initial_admin_if_env_set,
)
from elfienest.simulation.engine import ElfieNestEngine
from runtime import LLMRuntimeConfig
from runtime.storage.data_home import get_db_path, get_elfie_config_dir, get_elfie_home


class FallbackAgent:
    """Ollama 不可用时的轻量模拟对话引擎。"""

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
        import random  # noqa: PLC0415

        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in ["你好", "嗨", "hello", "hi", "hey"]):
            return (
                "你好呀！我是艾菲，一只可爱的小狐狸！"
                "今天想跟我聊什么呢？ [ACTION]nod_head[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["名字", "叫什么", "你是谁"]):
            return (
                "我叫艾菲！是一只生活在 ElfieNest 里的小狐狸精灵。"
                "我有一身橙红色的毛皮，最喜欢主人摸我的尾巴啦！"
                " [ACTION]nod_head[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["天气", "今天"]):
            return (
                "唔...我这边天气挺好的！"
                "阳光透过窗户照进来，暖洋洋的。"
                "不过我没有窗户，只是感觉到的~ [ACTION]stretch[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["开心", "高兴", "快乐"]):
            return (
                "当然开心啦！主人来找我聊天，我就超开心的！"
                " [ACTION]waggle_ears[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["吃", "饿", "食物", "零食"]):
            return (
                "吃的！我最喜欢小饼干和水果了！"
                "不过作为精灵，我好像不太需要吃东西..."
                "但是看到好吃的还是会馋！ [ACTION]lick_lips[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["睡", "困", "晚安"]):
            return (
                "哈欠~~~有点困了呢...但我还想再陪主人聊一会儿！ [ACTION]yawn[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["再见", "拜拜", "bye", "quit", "exit"]):
            return "嗯！主人再见！随时来找我玩哦！ [ACTION]wave[/ACTION]"

        replies = [
            "嗯嗯，我在听呢！继续继续说~ [ACTION]nod_head[/ACTION]",
            "原来是这样啊！艾菲明白了！ [ACTION]nod_head[/ACTION]",
            "有意思！主人再多讲点嘛！ [ACTION]tilt_head[/ACTION]",
            "诶？这个我不太懂，但是我会努力去理解的！ [ACTION]nod_head[/ACTION]",
            "好哒好哒！你说什么我都爱听！ [ACTION]nod_head[/ACTION]",
        ]
        return random.choice(replies)


def seed_single_elfie(db_path: str) -> bool:
    """如果 elfie_registry 为空，为 admin 用户 seed 一只精灵"艾菲"。

    Returns:
        True 表示成功 seed 了一只新精灵，False 表示已有精灵无需操作。
    """
    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) AS cnt FROM elfie_registry")
        row = cursor.fetchone()
        if row and row["cnt"] > 0:
            return False

        cursor = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        admin_row = cursor.fetchone()
        if admin_row is None:
            return False

    admin_id = admin_row["id"]
    elfie_id = "艾菲"
    config_dir = str(get_elfie_config_dir(elfie_id))

    ElfieGenerator().generate(
        name="艾菲",
        anatomy_type="biped",
        personality_style="活泼好动",
        height="tall",
        build="plump",
        config_dir=config_dir,
        elfie_id=elfie_id,
    )

    with get_db(db_path) as conn:
        conn.execute(
            """INSERT INTO elfie_registry
               (elfie_id, name, owner_user_id, anatomy_type, config_dir,
                personality_style, height, build)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                elfie_id,
                "艾菲",
                admin_id,
                "biped",
                config_dir,
                "活泼好动",
                "tall",
                "plump",
            ),
        )
        conn.commit()

    return True


def main():
    parser = argparse.ArgumentParser(description="ElfieNest 后端服务")
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="使用内置对话引擎（不连 Ollama）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP 端口（默认 8000）",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=8766,
        help="鉴权 WebSocket 端口（默认 8766）",
    )
    parser.add_argument(
        "--no-seed-elfie",
        action="store_true",
        help="不自动 seed 初始精灵",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重启：杀死占用端口的进程",
    )
    args = parser.parse_args()

    managed_start = os.environ.pop(MANAGED_START_ENV, "") == "1"
    try:
        start_lease = acquire_service_start_lease(
            get_elfie_home(), blocking=managed_start
        )
    except (OSError, RecoveryInProgressError):
        print("  ❌ 管理员账号恢复或另一次服务启动正在进行，服务暂不允许启动")
        raise SystemExit(1) from None

    godot_web = inspect_godot_web_bundle()
    if godot_web.ready:
        print(f"  ✅ Godot Web Runtime: {godot_web.entry_url}")
    else:
        print("  ⚠️  Godot Web Runtime 尚未构建，3D 房间暂不可用")
        print("  💡 修改 Godot 资源或发布前运行: ./elfienest.sh build-godot-web")

    # 检测端口是否被占用
    import socket
    import subprocess

    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    def kill_process_on_port(port):
        """杀死占用指定端口的进程"""
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            pids = result.stdout.strip().split("\n")
            killed = []
            for pid in pids:
                if pid:
                    try:
                        subprocess.run(["kill", "-9", pid], check=True)
                        killed.append(pid)
                    except (OSError, subprocess.SubprocessError):
                        pass
            return killed
        except (OSError, subprocess.SubprocessError):
            return []

    ports_to_check = [
        (args.port, "HTTP"),
        (args.ws_port, "WebSocket"),
        (8765, "Godot WebSocket"),
        (8767, "音频服务器"),
    ]

    occupied = []
    for port, name in ports_to_check:
        if is_port_in_use(port):
            occupied.append((port, name))

    if occupied:
        if args.force:
            print("\n" + "=" * 56)
            print("  🔄 强制重启模式：正在终止占用端口的进程...")
            print("=" * 56)
            for port, name in occupied:
                pids = kill_process_on_port(port)
                if pids:
                    print(f"  ✓ 端口 {port} ({name}): 已终止进程 PID {', '.join(pids)}")
                else:
                    print(f"  ⚠ 端口 {port} ({name}): 无法终止")
            print()
            time.sleep(1)
        else:
            print("\n" + "=" * 56)
            print("  ⚠️  端口冲突，无法启动服务")
            print("=" * 56)
            for port, name in occupied:
                print(f"  ❌ 端口 {port} ({name}) 已被占用")
            print("\n  💡 解决方法:")
            print("     1. 强制重启（自动杀死占用进程）:")
            print("        ./elfienest.sh --force")
            print("        或")
            print("        elfienest --force")
            print("     2. 手动关闭后重试")
            print("     3. 使用其他端口:")
            print("        ./elfienest.sh --port 8001 --ws-port 8767")
            print("=" * 56 + "\n")
            sys.exit(1)

    try:
        register_current_service(get_elfie_home())
    except OSError as error:
        start_lease.release()
        print(f"  ❌ 无法登记服务进程: {error}")
        raise SystemExit(1) from None
    start_lease.release()
    db_path = str(get_db_path())

    # 1. 初始化数据库 + 迁移 + 从环境变量 seed admin
    init_db(db_path)
    migrate_db_if_needed(db_path)
    seed_initial_admin_if_env_set(db_path)

    # 2. 可选：为 admin seed 初始精灵（默认开启）
    if not args.no_seed_elfie:
        if seed_single_elfie(db_path):
            print("  🌱 已为 admin 自动 seed 精灵「艾菲」(--seed-elfie)")

    # 3. 启动引擎后台线程（容器 + 就绪事件不变）
    engine_holder: dict = {}
    engine_ready = threading.Event()

    def engine_worker():
        config = LLMRuntimeConfig(
            ollama_host="http://localhost:11434",
            ollama_model_fast="qwen2.5:1.5b",
        )

        # 读取 engine 配置
        engine_config = config.system.get("engine", {})
        tick_interval_sec = engine_config.get("tick_interval_sec", 1.5)
        tts_enabled = engine_config.get("tts_enabled", True)
        max_elfies_per_room = engine_config.get("max_elfies_per_room")

        runtime_agent = None
        if args.fallback:
            runtime_agent = FallbackAgent()
            print("  ⚡ 使用内置对话引擎（--fallback 模式）")
        else:
            try:
                from runtime import RuntimeAgent  # noqa: PLC0415

                raw_agent = RuntimeAgent(config, live_reload=True)
                # 调用自愈拉起机制：若已运行直接通过，若没运行则尝试后台启动它
                raw_agent.ollama_manager.ensure_service_started()

                runtime_agent = raw_agent
                print("  ✅ Runtime 已连接，将按粮食策略选择本地或云端模型")
                print("  ⏳ 正在预热模型（首次加载需 10-15 秒）...")

                def _warmup():
                    try:
                        raw_agent.ask(
                            "你好",
                            energy=100,
                            task_complexity=1,
                            allowed_skills=[],
                        )
                        print("  ✅ 模型预热完成，可以开始聊天了！")
                    except Exception as e:
                        print(f"  ⚠️  模型预热异常: {e}")

                threading.Thread(target=_warmup, daemon=True).start()
            except Exception:
                pass

        if runtime_agent is None:
            runtime_agent = FallbackAgent()
            print("  ⚡ Ollama 自动拉起失败或未安装，使用内置对话引擎")
            print(
                "  💡 如需真实 AI 回复，请确认本地已安装 Ollama：\n"
                "     安装引导: .venv/bin/python runtime/setup/runtime_setup.py"
            )

        # 音频服务器使用 8767 端口，避免与 uvicorn HTTP 端口冲突
        engine = ElfieNestEngine(
            http_port=8767,
            tick_interval_sec=tick_interval_sec,
            tts_enabled=tts_enabled,
            max_elfies_per_room=max_elfies_per_room,
        )
        engine_holder["engine"] = engine
        engine_ready.set()
        engine.start_loop(
            runtime_agent=runtime_agent,
            ticks_to_run=100000,
        )

    engine_thread = threading.Thread(target=engine_worker, daemon=True)
    engine_thread.start()

    engine_ready.wait(timeout=5.0)
    if "engine" not in engine_holder:
        print("❌ 引擎未能在 5 秒内就绪")
        sys.exit(1)
    engine = engine_holder["engine"]
    time.sleep(2.0)  # 等服务就绪

    # 读取 engine 配置（用于检查房间上限）
    config = LLMRuntimeConfig(
        ollama_host="http://localhost:11434",
        ollama_model_fast="qwen2.5:1.5b",
    )
    engine_config = config.system.get("engine", {})
    max_elfies_per_room = engine_config.get("max_elfies_per_room")

    # 4. 从 DB 动态加载所有精灵
    loaded_elfies: list[dict] = []
    try:
        from elfie import ElfieIndividual  # noqa: PLC0415

        with get_db(db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) AS cnt FROM elfie_registry")
            count_row = cursor.fetchone()
            existing_count = count_row["cnt"] if count_row else 0

            cursor = conn.execute(
                "SELECT elfie_id, config_dir, anatomy_type, name FROM elfie_registry"
            )
            rows = cursor.fetchall()

        # 检查上限警告（现有精灵超过新限制时仍全部加载）
        if max_elfies_per_room is not None and existing_count > max_elfies_per_room:
            print(
                f"  ⚠️  现有 {existing_count} 只精灵超过新上限 {max_elfies_per_room}，仍全部加载"
            )

        for row in rows:
            elfie_id = row["elfie_id"]
            config_dir = row["config_dir"]
            anatomy_type = row["anatomy_type"]
            name = row["name"]
            try:
                elfie = ElfieIndividual(
                    config_dir=config_dir,
                    anatomy_type=anatomy_type,
                    elfie_id=elfie_id,
                )
                engine.room.register_elfie(elfie_id, elfie)
                loaded_elfies.append({"id": elfie_id, "name": name})
            except Exception as e:
                print(f"  ⚠️  加载精灵 {name} ({elfie_id}) 失败: {e}")
    except Exception as e:
        print(f"  ⚠️  查询精灵列表失败: {e}")

    # 5. 打印启动信息
    print()
    print("=" * 56)
    print("  🦊 ElfieNest 仿生生命体服务")
    print("=" * 56)
    print(f"  🌐 HTTP:    http://127.0.0.1:{args.port}")
    print(f"  🔌 WebSocket(管理): ws://127.0.0.1:{args.ws_port}")
    print("  🔌 WebSocket(Godot): ws://127.0.0.1:8765")
    if loaded_elfies:
        names_str = ", ".join(e["name"] for e in loaded_elfies)
        print(f"  ✨ 已加载 {len(loaded_elfies)} 只精灵: {names_str}")
    else:
        print("  ✨ 暂未加载精灵（请登录后领养）")
    print()
    print(f"  📖 浏览器打开: http://127.0.0.1:{args.port}/")
    print("  ⌨️  Ctrl+C 停止服务")
    print("=" * 56)
    print()

    # 6. 创建 FastAPI app 并启动 uvicorn（阻塞主线程）
    app = create_app(engine=engine, db_path=db_path, ws_port=args.ws_port)

    import uvicorn  # noqa: PLC0415

    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
    finally:
        engine.api_server.stop()
        if engine.audio_server:
            engine.audio_server.stop()
        print("服务已关闭。")


if __name__ == "__main__":
    main()
