#!/usr/bin/env python3
"""ElfieNest backend service — FastAPI + engine background thread + DB-driven dynamic Elfie loading.

Startup flow:
    1. Initialize DB + seed Owner account
    2. Optional: seed initial Elfie "Aifei" for Owner (--seed-elfie, default on)
    3. Engine background thread: RuntimeAgent → ElfieNestEngine (no hardcoded Elfies)
    4. Query elfie_registry from DB → instantiate Elfie → register to engine
    5. Create FastAPI app → uvicorn blocks main thread

Command-line arguments:
    --fallback      Use built-in dialogue engine (no Ollama connection)
    --port          HTTP port (default 8000)
    --ws-port       Auth WebSocket port (default 8766)
    --no-seed-elfie Do not auto-seed initial Elfie
    --force         Force restart (kill processes occupying ports)

CLI tools:
    .venv/bin/python scripts/elfienest.py config    Open config TUI
    .venv/bin/python scripts/elfienest.py owner     Manage Owner account
    .venv/bin/python scripts/elfienest.py doctor    Run local diagnostics
    .venv/bin/python scripts/elfienest.py status    View service status
    .venv/bin/python scripts/elfienest.py setup     First-time setup wizard
    .venv/bin/python scripts/elfienest.py restart   Restart service
    .venv/bin/python scripts/elfienest.py stop      Stop service
"""

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Protocol, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from ai_runtime import LLMRuntimeConfig
from ai_runtime.storage.data_home import (
    get_db_path,
    get_elfie_config_dir,
    get_elfie_home,
)
from app.features.adoption.generator import ElfieGenerator
from app.infrastructure.persistence.nest_state_repository import (
    SQLiteNestStateRepository,
)
from app.infrastructure.persistence.store import (
    get_db,
    init_db,
    migrate_db_if_needed,
    seed_initial_owner_if_env_set,
)
from app.interfaces.api.app import create_app
from app.interfaces.api.service_access import ServiceMode
from app.orchestration.engine import ElfieNestEngine
from app.orchestration.lifecycle.process import (
    DEFAULT_GODOT_WS_PORT,
    DEFAULT_MANAGEMENT_WS_PORT,
    DefaultProcessInspector,
    command_runs_service,
    register_current_service,
    validate_service_ports,
)
from app.orchestration.lifecycle.recovery_lock import (
    MANAGED_START_ENV,
    RecoveryInProgressError,
    acquire_service_start_lease,
)
from nest.godot.bundle import inspect_godot_web_bundle


class FallbackAgent:
    """Lightweight mock dialogue engine when Ollama is unavailable."""

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


def remaining_occupied_ports(
    occupied: Sequence[tuple[int, str]],
    is_port_in_use_func: Callable[[int], bool],
) -> list[tuple[int, str]]:
    """返回强制清理后仍然被占用的端口。"""
    return [(port, name) for port, name in occupied if is_port_in_use_func(port)]


def service_host(lan: bool) -> str:
    """Keep developer CLI loopback-only unless the caller explicitly enables LAN."""
    return "0.0.0.0" if lan else "127.0.0.1"


class GodotBuildCommandResult(Protocol):
    """最小化的 Godot 构建命令结果契约，便于无 Godot 单元测试。"""

    returncode: int


GodotBuildCommandRunner = Callable[[list[str]], GodotBuildCommandResult]


def prepare_godot_web_runtime(
    runtime_mode: str,
    run_command: GodotBuildCommandRunner = subprocess.run,
    is_frozen: bool = bool(getattr(sys, "frozen", False)),
) -> bool:
    """按运行模式确保或校验 Godot Web Runtime，返回是否可用。"""
    if runtime_mode == "release" and is_frozen:
        return True
    action = "--ensure" if runtime_mode == "development" else "--check"
    command = [
        sys.executable,
        str(Path(__file__).with_name("build_godot_web.py")),
        action,
    ]
    return run_command(command).returncode == 0


def seed_single_elfie(db_path: str) -> bool:
    """如果 elfie_registry 为空，为 Owner 用户 seed 一只精灵"艾菲"。

    Returns:
        True 表示成功 seed 了一只新精灵，False 表示已有精灵无需操作。
    """
    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) AS cnt FROM elfie_registry")
        row = cursor.fetchone()
        if row and row["cnt"] > 0:
            return False

        cursor = conn.execute(
            "SELECT id FROM users WHERE role = 'owner' ORDER BY id LIMIT 1"
        )
        owner_row = cursor.fetchone()
        if owner_row is None:
            return False

    owner_id = owner_row["id"]
    elfie_id = "elfie_default"
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
                owner_id,
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
    parser = argparse.ArgumentParser(description="ElfieNest backend service")
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Use built-in dialogue engine (no Ollama connection)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP port (default 8000)",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=DEFAULT_MANAGEMENT_WS_PORT,
        help="Auth WebSocket port (default 8766)",
    )
    parser.add_argument(
        "--godot-ws-port",
        type=int,
        default=DEFAULT_GODOT_WS_PORT,
        help="Godot WebSocket port (default 8765)",
    )
    parser.add_argument(
        "--no-seed-elfie",
        action="store_true",
        help="Do not auto-seed initial Elfie",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force restart: kill processes occupying ports",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Listen on LAN IPv4 address explicitly (default: localhost only)",
    )
    parser.add_argument(
        "--runtime-mode",
        choices=("development", "release"),
        default=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        help="Godot Web Runtime lifecycle mode (default: development)",
    )
    args = parser.parse_args()

    port_error = validate_service_ports(
        args.port,
        args.ws_port,
        args.godot_ws_port,
    )
    if port_error:
        parser.error(port_error)

    managed_start = os.environ.pop(MANAGED_START_ENV, "") == "1"
    try:
        start_lease = acquire_service_start_lease(
            get_elfie_home(), blocking=managed_start
        )
    except (OSError, RecoveryInProgressError):
        print("  ❌ Owner account recovery or another service start in progress, cannot start")
        raise SystemExit(1) from None

    godot_ready = prepare_godot_web_runtime(args.runtime_mode)
    if not godot_ready and args.runtime_mode == "release":
        print("  ❌ Release mode requires verified Godot Web Runtime, service not started")
        raise SystemExit(1)
    if not godot_ready:
        print(
            "  ⚠️  Godot Web Runtime auto-build failed, service still available for chat; please fix 3D preview via diagnostics"
        )

    godot_web = inspect_godot_web_bundle()
    if godot_web.ready:
        print(f"  ✅ Godot Web Runtime: {godot_web.entry_url}")
    else:
        print("  ⚠️  Godot Web Runtime 尚未构建，3D 房间暂不可用")
        print("  💡 修改 Godot 资源或发布前运行: ./elfienest.sh build-godot-web")

    # 检测端口是否被占用
    import socket

    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    def kill_process_on_port(port):
        """只终止当前项目登记的服务进程，保留外部监听者。"""
        inspector = DefaultProcessInspector()
        expected_root = Path(__file__).resolve().parent.parent
        expected_script = Path(__file__).resolve()
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
                        numeric_pid = int(pid)
                        process_cwd = inspector.cwd(numeric_pid).resolve()
                        process_command = inspector.command(numeric_pid)
                    except (OSError, ValueError, subprocess.SubprocessError):
                        continue
                    if process_cwd != expected_root or not command_runs_service(
                        process_command, process_cwd, expected_script
                    ):
                        continue
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
        (args.godot_ws_port, "Godot WebSocket"),
    ]

    occupied = []
    for port, name in ports_to_check:
        if is_port_in_use(port):
            occupied.append((port, name))

    if occupied:
        if args.force:
            print("\n" + "=" * 56)
            print("  🔄 Force restart mode: terminating processes on occupied ports...")
            print("=" * 56)
            for port, name in occupied:
                pids = kill_process_on_port(port)
                if pids:
                    print(f"  ✓ Port {port} ({name}): terminated process PID {', '.join(pids)}")
                else:
                    print(f"  ⚠ Port {port} ({name}): unable to terminate")
            print()
            time.sleep(1)
            remaining = remaining_occupied_ports(occupied, is_port_in_use)
            if remaining:
                print("=" * 56)
                print("  ❌ Force restart failed, ports still occupied")
                print("=" * 56)
                for port, name in remaining:
                    print(f"  ❌ Port {port} ({name}) still occupied")
                print("  Please manually close these processes and retry.")
                print("=" * 56 + "\n")
                start_lease.release()
                sys.exit(1)
        else:
            print("\n" + "=" * 56)
            print("  ⚠️  Port conflict, cannot start service")
            print("=" * 56)
            for port, name in occupied:
                print(f"  ❌ Port {port} ({name}) already in use")
            print("\n  💡 Solutions:")
            print("     1. Force restart (auto-kill occupying processes):")
            print("        ./elfienest.sh --force")
            print("        or")
            print("        elfienest --force")
            print("     2. Manually close and retry")
            print("     3. Use different ports:")
            print("        ./elfienest.sh --port 8001 --ws-port 8866")
            print("=" * 56 + "\n")
            start_lease.release()
            sys.exit(1)

    try:
        register_current_service(get_elfie_home())
    except OSError as error:
        start_lease.release()
        print(f"  ❌ Cannot register service process: {error}")
        raise SystemExit(1) from None
    start_lease.release()
    db_path = str(get_db_path())

    # 1. 初始化数据库 + 迁移 + 从环境变量 seed Owner
    init_db(db_path)
    migrate_db_if_needed(db_path)
    seed_initial_owner_if_env_set(db_path)

    # 2. 可选：为 Owner seed 初始精灵（默认开启）
    if not args.no_seed_elfie:
        if seed_single_elfie(db_path):
            print("  🌱 已为 Owner 自动 seed 精灵「艾菲」(--seed-elfie)")

    # 3. 启动引擎后台线程（容器 + 就绪事件不变）
    engine_holder: dict = {}
    engine_ready = threading.Event()

    def engine_worker():
        config = LLMRuntimeConfig(
            ollama_host="http://localhost:11434",
        )

        # 读取 engine 配置
        engine_config = config.system.get("engine", {})
        tick_interval_sec = engine_config.get("tick_interval_sec", 1.5)
        max_elfies_per_room = engine_config.get("max_elfies_per_room")

        runtime_agent = None
        if args.fallback:
            runtime_agent = FallbackAgent()
            print("  ⚡ Using built-in dialogue engine (--fallback mode)")
        else:
            try:
                from ai_runtime import RuntimeAgent  # noqa: PLC0415

                raw_agent = RuntimeAgent(config, live_reload=True)
                # 调用自愈拉起机制：若已运行直接通过，若没运行则尝试后台启动它
                raw_agent.ollama_manager.ensure_service_started()

                runtime_agent = raw_agent
                print("  ✅ Runtime connected, will select local or cloud models via food policy")
                print("  ⏳ Warming up model (first load takes 10-15 seconds)...")

                def _warmup():
                    try:
                        raw_agent.ask(
                            "你好",
                            energy=100,
                            task_complexity=1,
                            allowed_skills=[],
                        )
                        print("  ✅ Model warm-up complete, ready to chat!")
                    except Exception as e:
                        print(f"  ⚠️  Model warm-up error: {e}")

                threading.Thread(target=_warmup, daemon=True).start()
            except Exception:
                pass

        if runtime_agent is None:
            runtime_agent = FallbackAgent()
            print("  ⚡ Ollama auto-start failed or not installed, using built-in dialogue engine")
            print(
                "  💡 For real AI responses, ensure Ollama is installed locally:\n"
                "     Setup guide: .venv/bin/python ai_runtime/setup/runtime_setup.py"
            )

        engine = ElfieNestEngine(
            ws_port=args.godot_ws_port,
            godot_origin_port=args.port,
            tick_interval_sec=tick_interval_sec,
            max_elfies_per_room=max_elfies_per_room,
            nest_repository=SQLiteNestStateRepository(db_path),
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
    print("  ℹ️ Godot Web Runtime 由 ElfieNest Desktop 隐藏窗口托管")

    # 读取 engine 配置（用于检查房间上限）
    config = LLMRuntimeConfig(
        ollama_host="http://localhost:11434",
    )
    engine_config = config.system.get("engine", {})
    max_elfies_per_room = engine_config.get("max_elfies_per_room")

    engine.session.attach_repository(SQLiteNestStateRepository(db_path))

    # 4. 从 DB 动态加载所有精灵
    loaded_elfies: list[dict] = []
    try:
        from elfie import ElfieFactory  # noqa: PLC0415

        elfie_factory = ElfieFactory()

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
                elfie = elfie_factory.restore(
                    config_dir,
                    anatomy_type=anatomy_type,
                    godot_api=engine.api_server,
                    elfie_id=elfie_id,
                )
                engine.session.register_elfie(elfie_id, elfie)
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
    print(f"  🔌 WebSocket(Godot): ws://127.0.0.1:{args.godot_ws_port}")
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
    app = create_app(
        engine=engine,
        db_path=db_path,
        ws_port=args.ws_port,
        http_port=args.port,
        service_mode=ServiceMode.LAN.value if args.lan else ServiceMode.LOOPBACK.value,
    )

    import uvicorn  # noqa: PLC0415

    try:
        uvicorn.run(
            app,
            host=service_host(args.lan),
            limit_concurrency=100,
            port=args.port,
            log_level="warning",
        )
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
    finally:
        engine.api_server.stop()
        print("服务已关闭。")


if __name__ == "__main__":
    main()
