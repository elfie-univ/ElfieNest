#!/usr/bin/env python3
"""ElfieNest CLI - 仿生生命体系统命令行工具

用法:
    elfie                    启动服务（默认）
    elfie config             交互式配置
    elfie models             列出可用模型
    elfie providers          管理 providers
    elfie status             查看服务状态
    elfie web                启动服务并打开浏览器
    elfie stats              显示使用统计
    elfie session            管理会话
    elfie logs               查看日志
    elfie db                 数据库工具
    elfie version            显示版本
    elfie setup              首次设置向导
    elfie restart            重启服务
    elfie stop               停止服务
"""
import argparse
import json
import os
import sys
import subprocess
import sqlite3
import webbrowser
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_FILE = "runtime/runtime_config.json"
VERSION = "1.0.0"

def print_banner():
    CYAN = "\033[1;36m"
    YELLOW = "\033[1;33m"
    RESET = "\033[0m"
    banner = (
        f"{CYAN}███████╗██╗     ███████╗██╗███████╗     {YELLOW}███╗   ██╗███████╗███████╗████████╗{RESET}\n"
        f"{CYAN}██╔════╝██║     ██╔════╝██║██╔════╝     {YELLOW}████╗  ██║██╔════╝██╔════╝╚══██╔══╝{RESET}\n"
        f"{CYAN}█████╗  ██║     █████╗  ██║█████╗       {YELLOW}██╔██╗ ██║█████╗  ███████╗   ██║   {RESET}\n"
        f"{CYAN}██╔══╝  ██║     ██╔══╝  ██║██╔══╝       {YELLOW}██║╚██╗██║██╔══╝  ╚════██║   ██║   {RESET}\n"
        f"{CYAN}███████╗███████╗██║     ██║███████╗     {YELLOW}██║ ╚████║███████╗███████║   ██║   {RESET}\n"
        f"{CYAN}╚══════╝╚══════╝╚═╝     ╚═╝╚══════╝     {YELLOW}╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝   {RESET}\n"
        "\n            🦊 仿生生命体系统 - Embodied AI Creature Simulation\n"
    )
    print(banner)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def input_text(prompt, default=None):
    hint = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{hint}: ").strip()
        return value if value else default
    except KeyboardInterrupt:
        return default

def config_tui():
    """配置主菜单 TUI"""
    while True:
        clear_screen()
        print_banner()
        config = load_config()
        
        print("  📋 配置菜单")
        print("  " + "=" * 45)
        print("  1. 查看当前配置")
        print("  2. 配置大模型 (LLM)")
        print("  3. 配置引擎参数")
        print("  4. 配置安全设置")
        print("  5. 配置精灵领养")
        print("  6. 测试配置")
        print("  7. 重置为默认配置")
        print("  0. 退出")
        print()
        
        try:
            choice = input("请选择 [0-7]: ").strip()
        except KeyboardInterrupt:
            print("\n再见！")
            break
        
        if choice == "0":
            print("\n再见！")
            break
        elif choice == "1":
            show_config(config)
        elif choice == "2":
            config_llm(config)
        elif choice == "3":
            config_engine(config)
        elif choice == "4":
            config_security(config)
        elif choice == "5":
            config_adoption(config)
        elif choice == "6":
            test_config(config)
        elif choice == "7":
            reset_config()

def show_config(config):
    """显示当前配置"""
    clear_screen()
    print_banner()
    print("  📄 当前配置")
    print("  " + "=" * 45)
    print()
    
    llm = config.get("system", {}).get("llm", {})
    print("  【大模型配置】")
    print(f"    轻量模型: {llm.get('default_cheap_model', 'qwen3.5:0.8b')}")
    print(f"    深度模型: {llm.get('default_deep_model', 'qwen3.5:0.8b')}")
    print(f"    多模态模型: {llm.get('default_multimodal_model', 'qwen2.5:7b')}")
    print(f"    服务商: {llm.get('default_cheap_provider', 'ollama')}")
    print()
    
    engine = config.get("system", {}).get("engine", {})
    print("  【引擎配置】")
    print(f"    Tick 间隔: {engine.get('tick_interval_sec', 1.5)} 秒")
    print(f"    TTS 启用: {engine.get('tts_enabled', True)}")
    print(f"    房间精灵上限: {engine.get('max_elfies_per_room', 10)}")
    print()
    
    security = config.get("system", {}).get("security", {})
    print("  【安全配置】")
    print(f"    Session TTL: {security.get('session_ttl_hours', 24)} 小时")
    print(f"    速率限制: {security.get('rate_limit_per_minute', 60)}/分钟")
    print()
    
    adoption = config.get("system", {}).get("adoption", {})
    print("  【领养配置】")
    print(f"    每用户精灵上限: {adoption.get('max_elfies_per_user', 3)}")
    print(f"    默认性格: {adoption.get('default_personality_style', '活泼好动')}")
    print()
    
    input("\n按回车键继续...")

def config_llm(config):
    """配置大模型"""
    while True:
        clear_screen()
        print_banner()
        print("  🤖 大模型配置")
        print("  " + "=" * 45)
        
        llm = config.setdefault("system", {}).setdefault("llm", {})
        
        print(f"  1. 轻量模型: {llm.get('default_cheap_model', 'qwen3.5:0.8b')}")
        print(f"  2. 深度模型: {llm.get('default_deep_model', 'qwen3.5:0.8b')}")
        print(f"  3. 多模态模型: {llm.get('default_multimodal_model', 'qwen2.5:7b')}")
        print(f"  4. 服务商: {llm.get('default_cheap_provider', 'ollama')}")
        print("  0. 保存并返回")
        print()
        
        try:
            choice = input("请选择 [0-4]: ").strip()
        except KeyboardInterrupt:
            return
        
        if choice == "0":
            save_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        elif choice == "1":
            value = input_text("请输入轻量模型名称", llm.get('default_cheap_model', 'qwen3.5:0.8b'))
            if value:
                llm['default_cheap_model'] = value
        elif choice == "2":
            value = input_text("请输入深度模型名称", llm.get('default_deep_model', 'qwen3.5:0.8b'))
            if value:
                llm['default_deep_model'] = value
        elif choice == "3":
            value = input_text("请输入多模态模型名称", llm.get('default_multimodal_model', 'qwen2.5:7b'))
            if value:
                llm['default_multimodal_model'] = value
        elif choice == "4":
            providers = ["ollama", "openai", "deepseek", "gemini", "qwen"]
            print("\n可用服务商:")
            for i, p in enumerate(providers, 1):
                print(f"  {i}. {p}")
            try:
                idx = int(input("请选择 [1-5]: ")) - 1
                if 0 <= idx < len(providers):
                    llm['default_cheap_provider'] = providers[idx]
                    llm['default_deep_provider'] = providers[idx]
            except:
                pass

def config_engine(config):
    """配置引擎参数"""
    while True:
        clear_screen()
        print_banner()
        print("  ⚙️  引擎配置")
        print("  " + "=" * 45)
        
        engine = config.setdefault("system", {}).setdefault("engine", {})
        
        print(f"  1. Tick 间隔 (秒): {engine.get('tick_interval_sec', 1.5)}")
        print(f"  2. TTS 语音合成: {'启用' if engine.get('tts_enabled', True) else '禁用'}")
        print(f"  3. 房间精灵上限: {engine.get('max_elfies_per_room', 10)}")
        print("  0. 保存并返回")
        print()
        
        try:
            choice = input("请选择 [0-3]: ").strip()
        except KeyboardInterrupt:
            return
        
        if choice == "0":
            save_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        elif choice == "1":
            try:
                value = float(input_text("请输入 Tick 间隔 (秒)", str(engine.get('tick_interval_sec', 1.5))))
                engine['tick_interval_sec'] = value
            except:
                print("❌ 输入无效")
        elif choice == "2":
            engine['tts_enabled'] = not engine.get('tts_enabled', True)
        elif choice == "3":
            try:
                value = int(input_text("请输入房间精灵上限", str(engine.get('max_elfies_per_room', 10))))
                engine['max_elfies_per_room'] = value
            except:
                print("❌ 输入无效")

def config_security(config):
    """配置安全设置"""
    while True:
        clear_screen()
        print_banner()
        print("  🔒 安全配置")
        print("  " + "=" * 45)
        
        security = config.setdefault("system", {}).setdefault("security", {})
        
        print(f"  1. Session 有效期 (小时): {security.get('session_ttl_hours', 24)}")
        print(f"  2. 速率限制 (次/分钟): {security.get('rate_limit_per_minute', 60)}")
        print("  0. 保存并返回")
        print()
        
        try:
            choice = input("请选择 [0-2]: ").strip()
        except KeyboardInterrupt:
            return
        
        if choice == "0":
            save_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        elif choice == "1":
            try:
                value = int(input_text("请输入 Session 有效期 (小时)", str(security.get('session_ttl_hours', 24))))
                security['session_ttl_hours'] = value
            except:
                print("❌ 输入无效")
        elif choice == "2":
            try:
                value = int(input_text("请输入速率限制 (次/分钟)", str(security.get('rate_limit_per_minute', 60))))
                security['rate_limit_per_minute'] = value
            except:
                print("❌ 输入无效")

def config_adoption(config):
    """配置精灵领养"""
    while True:
        clear_screen()
        print_banner()
        print("  🐾 精灵领养配置")
        print("  " + "=" * 45)
        
        adoption = config.setdefault("system", {}).setdefault("adoption", {})
        
        print(f"  1. 每用户精灵上限: {adoption.get('max_elfies_per_user', 3)}")
        print(f"  2. 默认性格风格: {adoption.get('default_personality_style', '活泼好动')}")
        print("  0. 保存并返回")
        print()
        
        try:
            choice = input("请选择 [0-2]: ").strip()
        except KeyboardInterrupt:
            return
        
        if choice == "0":
            save_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        elif choice == "1":
            try:
                value = int(input_text("请输入每用户精灵上限", str(adoption.get('max_elfies_per_user', 3))))
                adoption['max_elfies_per_user'] = value
            except:
                print("❌ 输入无效")
        elif choice == "2":
            styles = ["活泼好动", "温顺乖巧", "高冷傲娇", "憨厚老实", "机灵古怪"]
            print("\n可用性格风格:")
            for i, s in enumerate(styles, 1):
                print(f"  {i}. {s}")
            try:
                idx = int(input("请选择 [1-5]: ")) - 1
                if 0 <= idx < len(styles):
                    adoption['default_personality_style'] = styles[idx]
            except:
                pass

def test_config(config):
    """测试配置"""
    clear_screen()
    print_banner()
    print("  🧪 测试配置")
    print("  " + "=" * 45)
    print()
    
    print("  [1/3] 测试 Ollama 连接...")
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
        if resp.status == 200:
            print("  ✅ Ollama 连接成功")
        else:
            print("  ❌ Ollama 响应异常")
    except:
        print("  ⚠️  Ollama 未运行（将使用 fallback 模式）")
    
    print("\n  [2/3] 测试数据库...")
    try:
        conn = sqlite3.connect("data/nest.db")
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        print(f"  ✅ 数据库正常（{count} 个用户）")
        conn.close()
    except Exception as e:
        print(f"  ❌ 数据库错误: {e}")
    
    print("\n  [3/3] 测试配置文件...")
    if os.path.exists(CONFIG_FILE):
        print(f"  ✅ 配置文件存在: {CONFIG_FILE}")
    else:
        print("  ⚠️  配置文件不存在（将使用默认配置）")
    
    print("\n✅ 测试完成")
    input("\n按回车键继续...")

def reset_config():
    """重置配置"""
    print("\n⚠️  这将重置所有配置为默认值，是否继续？")
    choice = input("输入 'yes' 确认: ").strip()
    if choice.lower() == 'yes':
        default_config = {
            "system": {
                "llm": {
                    "default_cheap_model": "qwen3.5:0.8b",
                    "default_deep_model": "qwen3.5:0.8b",
                    "default_multimodal_model": "qwen2.5:7b",
                    "default_cheap_provider": "ollama",
                    "default_deep_provider": "ollama"
                },
                "engine": {
                    "tick_interval_sec": 1.5,
                    "tts_enabled": True,
                    "max_elfies_per_room": 10
                },
                "security": {
                    "session_ttl_hours": 24,
                    "rate_limit_per_minute": 60
                },
                "adoption": {
                    "max_elfies_per_user": 3,
                    "default_personality_style": "活泼好动"
                }
            }
        }
        save_config(default_config)
        print("✅ 配置已重置")
    else:
        print("已取消")
    input("\n按回车键继续...")

def cmd_models():
    """列出可用模型"""
    print("  📋 可用模型列表")
    print("  " + "=" * 45)
    print()
    
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
        data = json.loads(resp.read().decode())
        models = data.get("models", [])
        
        if models:
            print("  【Ollama 本地模型】")
            for m in models:
                name = m.get("name", "")
                size = m.get("size", 0) / (1024**3)
                print(f"    • {name} ({size:.1f} GB)")
        else:
            print("  ⚠️  Ollama 中没有模型")
            print("  💡 使用 'ollama pull qwen3.5:0.8b' 下载模型")
    except Exception as e:
        print(f"  ❌ 无法连接 Ollama: {e}")
    
    print()
    print("  【推荐模型】")
    print("    • qwen3.5:0.8b  - 轻量级，快速响应")
    print("    • qwen2.5:7b    - 深度思考，质量更高")
    print("    • llama3.2:3b   - Meta Llama 3.2")
    print()

def cmd_providers():
    """管理 providers"""
    print("  🔑 Providers 管理")
    print("  " + "=" * 45)
    print()
    
    config = load_config()
    llm = config.get("system", {}).get("llm", {})
    
    print("  当前配置:")
    print(f"    服务商: {llm.get('default_cheap_provider', 'ollama')}")
    print()
    print("  可用服务商:")
    print("    1. ollama    - 本地运行，免费")
    print("    2. openai    - OpenAI API")
    print("    3. deepseek  - DeepSeek API")
    print("    4. gemini    - Google Gemini API")
    print("    5. qwen      - 通义千问 API")
    print()
    
    print("  💡 配置 API Key:")
    print("     export OPENAI_API_KEY='sk-xxx'")
    print("     export DEEPSEEK_API_KEY='sk-xxx'")
    print("     export GEMINI_API_KEY='xxx'")
    print("     export QWEN_API_KEY='sk-xxx'")
    print()

def cmd_status():
    """查看服务状态"""
    print("  📊 服务状态")
    print("  " + "=" * 45)
    print()
    
    import socket
    ports = [
        (8000, "HTTP 服务"),
        (8766, "WebSocket (管理)"),
        (8765, "WebSocket (Godot)"),
    ]
    
    for port, name in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                print(f"  ✅ {name}: 运行中 (端口 {port})")
            else:
                print(f"  ⭕ {name}: 未运行 (端口 {port})")
    
    print()
    try:
        conn = sqlite3.connect("data/nest.db")
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM elfie_registry")
        elfie_count = cursor.fetchone()[0]
        print(f"  📦 数据库: {user_count} 用户, {elfie_count} 精灵")
        conn.close()
    except:
        print("  ❌ 数据库未初始化")
    
    print()

def cmd_web():
    """启动服务并打开浏览器"""
    print("  🌐 启动服务并打开浏览器...")
    print()
    
    # 启动服务
    subprocess.Popen(
        [sys.executable, 'scripts/serve.py', '--fallback'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    import time
    time.sleep(3)
    
    # 打开浏览器
    url = "http://localhost:8000/static/login.html"
    print(f"  打开浏览器: {url}")
    webbrowser.open(url)
    
    print("  ✅ 服务已启动")
    print()

def cmd_stats():
    """显示使用统计"""
    print("  📈 使用统计")
    print("  " + "=" * 45)
    print()
    
    try:
        conn = sqlite3.connect("data/nest.db")
        
        # 用户统计
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        admin_count = cursor.fetchone()[0]
        
        # 精灵统计
        cursor = conn.execute("SELECT COUNT(*) FROM elfie_registry")
        elfie_count = cursor.fetchone()[0]
        
        cursor = conn.execute("""
            SELECT anatomy_type, COUNT(*) 
            FROM elfie_registry 
            GROUP BY anatomy_type
        """)
        anatomy_stats = dict(cursor.fetchall())
        
        # 会话统计
        cursor = conn.execute("SELECT COUNT(*) FROM sessions")
        session_count = cursor.fetchone()[0]
        
        print("  【用户统计】")
        print(f"    总用户数: {user_count}")
        print(f"    管理员数: {admin_count}")
        print(f"    普通用户: {user_count - admin_count}")
        print()
        
        print("  【精灵统计】")
        print(f"    总精灵数: {elfie_count}")
        for anatomy, count in anatomy_stats.items():
            print(f"    {anatomy}: {count}")
        print()
        
        print("  【会话统计】")
        print(f"    活跃会话: {session_count}")
        print()
        
        conn.close()
    except Exception as e:
        print(f"  ❌ 无法读取统计: {e}")
    
    print()

def cmd_session():
    """管理会话"""
    print("  👥 会话管理")
    print("  " + "=" * 45)
    print()
    
    try:
        conn = sqlite3.connect("data/nest.db")
        cursor = conn.execute("""
            SELECT s.token, u.username, s.created_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            ORDER BY s.created_at DESC
            LIMIT 20
        """)
        sessions = cursor.fetchall()
        
        if sessions:
            print("  【在线用户】")
            for token, username, created in sessions:
                token_short = token[:8] + "..."
                print(f"    • {username} (token: {token_short}, 登录: {created})")
        else:
            print("  暂无活跃会话")
        
        conn.close()
    except Exception as e:
        print(f"  ❌ 无法读取会话: {e}")
    
    print()

def cmd_logs():
    """查看日志"""
    print("  📝 日志查看")
    print("  " + "=" * 45)
    print()
    
    log_files = [
        "/tmp/serve.log",
        "/tmp/serve_full.log",
        "/tmp/final_serve.log",
    ]
    
    for log_file in log_files:
        if os.path.exists(log_file):
            print(f"  【{log_file}】")
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()[-20:]
                    for line in lines:
                        print(f"    {line.rstrip()}")
            except:
                print("    无法读取")
            print()
    
    print("  💡 查看完整日志: tail -100 /tmp/serve.log")
    print()

def cmd_db(args):
    """数据库工具"""
    print("  🗄️  数据库工具")
    print("  " + "=" * 45)
    print()
    
    if hasattr(args, 'db_command') and args.db_command == 'backup':
        # 备份数据库
        backup_path = f"data/nest.db.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            import shutil
            shutil.copy("data/nest.db", backup_path)
            print(f"  ✅ 数据库已备份到: {backup_path}")
        except Exception as e:
            print(f"  ❌ 备份失败: {e}")
    elif hasattr(args, 'db_command') and args.db_command == 'reset':
        # 重置数据库
        print("  ⚠️  这将删除所有数据，是否继续？")
        choice = input("输入 'yes' 确认: ").strip()
        if choice.lower() == 'yes':
            try:
                os.remove("data/nest.db")
                print("  ✅ 数据库已删除，重启服务将自动创建新数据库")
            except Exception as e:
                print(f"  ❌ 删除失败: {e}")
    else:
        print("  可用命令:")
        print("    elfie db backup  - 备份数据库")
        print("    elfie db reset   - 重置数据库")
        print()
        
        # 显示数据库信息
        try:
            conn = sqlite3.connect("data/nest.db")
            
            # 表信息
            cursor = conn.execute("""
                SELECT name FROM sqlite_master WHERE type='table'
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            print("  【数据库表】")
            for table in tables:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"    • {table}: {count} 条记录")
            
            conn.close()
        except Exception as e:
            print(f"  ❌ 无法读取数据库: {e}")
    
    print()

def cmd_version():
    """显示版本"""
    print(f"  ElfieNest v{VERSION}")
    print()
    print("  🦊 仿生生命体系统")
    print("  一个基于三层大脑架构的 AI 生物模拟系统")
    print()

def cmd_setup():
    """首次设置向导"""
    clear_screen()
    print_banner()
    print("  ✨ 欢迎使用 ElfieNest 设置向导")
    print("  " + "=" * 45)
    print()
    
    try:
        conn = sqlite3.connect("data/nest.db")
        cursor = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        if cursor.fetchone()[0] > 0:
            print("  ⚠️  系统已初始化，跳过设置向导")
            conn.close()
            return
        conn.close()
    except:
        pass
    
    print("  让我们开始配置你的 ElfieNest 系统...")
    print()
    
    print("  【步骤 1/3】创建管理员账号")
    print()
    username = input_text("  管理员用户名", "admin")
    password = input_text("  管理员密码", "admin123")
    print()
    
    print("  【步骤 2/3】配置大模型")
    print()
    print("  检测 Ollama...")
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
        print("  ✅ Ollama 已运行")
    except:
        print("  ⚠️  Ollama 未运行，将使用 fallback 模式")
    print()
    
    print("  【步骤 3/3】初始化数据库")
    print()
    from elfienest.manage.store import init_db, migrate_db_if_needed, hash_password
    
    init_db("data/nest.db")
    migrate_db_if_needed("data/nest.db")
    
    conn = sqlite3.connect("data/nest.db")
    hashed = hash_password(password)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (username, hashed)
        )
        conn.commit()
        print(f"  ✅ 管理员 '{username}' 创建成功")
    except Exception as e:
        print(f"  ⚠️  管理员已存在或创建失败: {e}")
    conn.close()
    
    print()
    print("  " + "=" * 45)
    print("  ✅ 设置完成！")
    print()
    print("  启动服务: elfie")
    print(f"  登录信息: {username} / {password}")
    print()

def cmd_restart():
    """重启服务"""
    print("  🔄 重启服务...")
    
    try:
        subprocess.run(['pkill', '-f', 'serve.py'], capture_output=True)
        print("  ✓ 已停止旧服务")
    except:
        pass
    
    import time
    time.sleep(1)
    
    print("  ✓ 启动新服务...")
    subprocess.Popen(
        [sys.executable, 'scripts/serve.py', '--fallback'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    time.sleep(3)
    print("  ✅ 服务已重启")

def cmd_stop():
    """停止服务"""
    print("  🛑 停止服务...")
    try:
        subprocess.run(['pkill', '-f', 'serve.py'], check=True)
        print("  ✅ 服务已停止")
    except:
        print("  ⚠️  服务未运行")

def main():
    parser = argparse.ArgumentParser(
        description="ElfieNest CLI - 仿生生命体系统命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    subparsers.add_parser("config", help="交互式配置 TUI")
    subparsers.add_parser("models", help="列出可用模型")
    subparsers.add_parser("providers", help="管理 providers")
    subparsers.add_parser("status", help="查看服务状态")
    subparsers.add_parser("web", help="启动服务并打开浏览器")
    subparsers.add_parser("stats", help="显示使用统计")
    subparsers.add_parser("session", help="管理会话")
    subparsers.add_parser("logs", help="查看日志")
    subparsers.add_parser("version", help="显示版本")
    subparsers.add_parser("setup", help="首次设置向导")
    subparsers.add_parser("restart", help="重启服务")
    subparsers.add_parser("stop", help="停止服务")
    
    # db 子命令
    db_parser = subparsers.add_parser("db", help="数据库工具")
    db_parser.add_argument("db_command", nargs="?", choices=["backup", "reset"], help="数据库命令")
    
    args = parser.parse_args()
    
    if args.command == "config":
        config_tui()
    elif args.command == "models":
        cmd_models()
    elif args.command == "providers":
        cmd_providers()
    elif args.command == "status":
        cmd_status()
    elif args.command == "web":
        cmd_web()
    elif args.command == "stats":
        cmd_stats()
    elif args.command == "session":
        cmd_session()
    elif args.command == "logs":
        cmd_logs()
    elif args.command == "db":
        cmd_db(args)
    elif args.command == "version":
        cmd_version()
    elif args.command == "setup":
        cmd_setup()
    elif args.command == "restart":
        cmd_restart()
    elif args.command == "stop":
        cmd_stop()
    else:
        # 默认：启动服务
        print_banner()
        print("  启动服务...")
        print()
        os.execvp(sys.executable, [sys.executable, 'scripts/serve.py'] + sys.argv[1:])

if __name__ == "__main__":
    main()
