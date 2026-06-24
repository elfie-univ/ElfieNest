#!/usr/bin/env python3
"""ElfieNest CLI - 仿生生命体系统命令行工具

用法:
    elfie                    启动服务（默认）
    elfie config             交互式配置
    elfie models [list|scan] 列出/扫描模型
    elfie providers [list|test|add|remove] 管理 providers
    elfie login <provider>   配置服务商 API Key
    elfie route show <elfie_id> 显示模型路由
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
import getpass
import json
import os
import subprocess
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.data_home import get_config_path, get_db_path, get_elfie_config_dir, get_elfie_home, get_env_path
from runtime.provider_profiles import BUILTIN_PROFILES, get_profile
from runtime.model_catalog import BUILTIN_MODEL_CATALOG, verify_provider
from runtime.model_route import load_model_route, SCENE_SLOTS
from runtime.config import LLMRuntimeConfig

CONFIG_FILE = str(get_config_path())
VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


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


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(config: Dict[str, Any]):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def load_env() -> Dict[str, str]:
    env_path = get_env_path()
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars


def save_env(env_vars: Dict[str, str]):
    env_path = get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write("# ElfieNest 环境变量 - API Keys\n")
        f.write("# 此文件已 gitignore，请勿提交到版本库\n\n")
        for key, value in sorted(env_vars.items()):
            f.write(f"{key}={value}\n")
    os.chmod(env_path, 0o600)

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')


def input_text(prompt: str, default: Optional[str] = None) -> Optional[str]:
    hint = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{hint}: ").strip()
        return value if value else default
    except KeyboardInterrupt:
        return default


def input_password(prompt: str) -> Optional[str]:
    try:
        return getpass.getpass(prompt + ": ")
    except KeyboardInterrupt:
        return None


# ---------------------------------------------------------------------------
# 新增命令: elfie login <provider>
# ---------------------------------------------------------------------------


def cmd_login(args):
    provider_id = args.provider

    profile = get_profile(provider_id)
    if not profile:
        print(f"❌ 未知服务商: {provider_id}")
        print("\n可用服务商:")
        for pid, p in BUILTIN_PROFILES.items():
            print(f"  • {pid:12s} - {p.name}")
        return

    print(f"\n🔑 配置 {profile.name} 服务商\n")

    api_key = ""
    if profile.api_key_env_var:
        api_key = input_password(f"  API Key")
        if not api_key:
            print("❌ API Key 不能为空")
            return
    else:
        print("  ℹ️  Ollama 无需 API Key，跳过")

    base_url_default = profile.api_base
    base_url_hint = f"回车使用默认 {base_url_default}"
    base_url_input = input_text(f"  Base URL ({base_url_hint})")
    base_url = base_url_input if base_url_input else base_url_default

    print("\n  ⏳ 验证连通性...")

    temp_config = LLMRuntimeConfig()
    temp_config.providers[provider_id] = {
        "api_key": api_key,
        "api_base": base_url,
        "api_mode": profile.api_mode,
        "status": "inactive",
    }

    result = verify_provider(provider_id, temp_config)

    if result["status"] == "active":
        latency = result.get("latency_ms", 0)
        print(f"  ✅ 连通性验证成功！延迟: {latency:.0f}ms\n")

        config = load_config()
        if "providers" not in config:
            config["providers"] = {}
        config["providers"][provider_id] = {
            "api_base": base_url,
            "api_mode": profile.api_mode,
            "status": "active",
        }
        save_config(config)

        if profile.api_key_env_var and api_key:
            env_vars = load_env()
            env_vars[profile.api_key_env_var] = api_key
            if profile.base_url_env_var and base_url != profile.api_base:
                env_vars[profile.base_url_env_var] = base_url
            save_env(env_vars)

        print(f"  ✅ {profile.name} 配置已保存")
    else:
        error = result.get("error", "未知错误")
        print(f"  ❌ 连通性验证失败: {error}")
        print("\n  请检查:")
        print("    • API Key 是否正确")
        print("    • Base URL 是否可访问")
        print("    • 网络连接是否正常")


# ---------------------------------------------------------------------------
# 新增命令: elfie providers [list|test|add|remove]
# ---------------------------------------------------------------------------


def cmd_providers(args):
    subcmd = args.providers_command or "list"

    if subcmd == "list":
        cmd_providers_list()
    elif subcmd == "test":
        cmd_providers_test(args)
    elif subcmd == "add":
        cmd_providers_add(args)
    elif subcmd == "remove":
        cmd_providers_remove(args)


def cmd_providers_list():
    print("\n  📋 服务商列表\n")

    config = load_config()
    providers_config = config.get("providers", {})

    print(f"  {'ID':<12s} {'名称':<20s} {'状态':<8s} {'API模式':<20s}")
    print("  " + "-" * 70)

    for provider_id, profile in BUILTIN_PROFILES.items():
        provider_info = providers_config.get(provider_id, {})
        status = provider_info.get("status", "inactive")
        api_mode = profile.api_mode

        status_icon = "✅" if status == "active" else "⭕"
        status_text = f"{status_icon} {status}"

        print(f"  {provider_id:<12s} {profile.name:<20s} {status_text:<8s} {api_mode:<20s}")

    print()


def cmd_providers_test(args):
    provider_id = args.provider_id

    profile = get_profile(provider_id)
    if not profile:
        print(f"❌ 未知服务商: {provider_id}")
        return

    print(f"\n  ⏳ 测试 {profile.name} 连通性...\n")

    config = LLMRuntimeConfig.load()
    result = verify_provider(provider_id, config)

    if result["status"] == "active":
        latency = result.get("latency_ms", 0)
        print(f"  ✅ {profile.name} 可用，延迟: {latency:.0f}ms")
    else:
        error = result.get("error", "未知错误")
        print(f"  ❌ {profile.name} 不可用: {error}")

    print()


def cmd_providers_add(args):
    provider_id = args.provider_id

    profile = get_profile(provider_id)
    if not profile:
        print(f"❌ 未知服务商: {provider_id}")
        print("\n可用服务商:")
        for pid, p in BUILTIN_PROFILES.items():
            print(f"  • {pid:12s} - {p.name}")
        return

    login_args = argparse.Namespace(provider=provider_id)
    cmd_login(login_args)


def cmd_providers_remove(args):
    provider_id = args.provider_id

    profile = get_profile(provider_id)
    if not profile:
        print(f"❌ 未知服务商: {provider_id}")
        return

    config = load_config()
    if "providers" in config and provider_id in config["providers"]:
        del config["providers"][provider_id]
        save_config(config)
        print(f"  ✅ 已从 config.yaml 移除 {profile.name}")

    if profile.api_key_env_var:
        env_vars = load_env()
        if profile.api_key_env_var in env_vars:
            del env_vars[profile.api_key_env_var]
            save_env(env_vars)
            print(f"  ✅ 已从 .env 移除 {profile.api_key_env_var}")

    print(f"\n  ✅ {profile.name} 配置已移除")


# ---------------------------------------------------------------------------
# 新增命令: elfie models [list|scan]
# ---------------------------------------------------------------------------


def cmd_models(args):
    subcmd = args.models_command or "list"

    if subcmd == "list":
        cmd_models_list()
    elif subcmd == "scan":
        cmd_models_scan()


def cmd_models_list():
    print("\n  📦 模型目录\n")

    config = load_config()
    providers_config = config.get("providers", {})

    print(f"  {'模型ID':<35s} {'能力':<25s} {'费用等级':<8s} {'状态':<8s}")
    print("  " + "-" * 85)

    for model_id, entry in BUILTIN_MODEL_CATALOG.items():
        if not entry.visible:
            continue

        caps = ", ".join(entry.capabilities[:3])
        if len(entry.capabilities) > 3:
            caps += "..."

        cost_tiers = ["免费", "极低", "低", "中", "高"]
        cost_text = cost_tiers[entry.cost_tier] if entry.cost_tier < len(cost_tiers) else "未知"

        provider = entry.provider
        if provider == "ollama":
            status = "✅ 可用"
        else:
            provider_info = providers_config.get(provider, {})
            status = "✅ 可用" if provider_info.get("status") == "active" else "⭕ 未配置"

        print(f"  {model_id:<35s} {caps:<25s} {cost_text:<8s} {status:<8s}")

    print()


def cmd_models_scan():
    print("\n  🔍 扫描 Ollama 本地模型...\n")

    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5.0)
        data = json.loads(resp.read().decode())
        models = data.get("models", [])

        if not models:
            print("  ⚠️  Ollama 中没有模型")
            print("  💡 使用 'ollama pull qwen3.5:0.8b' 下载模型")
            return

        print(f"  发现 {len(models)} 个本地模型:\n")
        print(f"  {'模型名称':<30s} {'大小':<12s} {'修改时间'}")
        print("  " + "-" * 70)

        for m in models:
            name = m.get("name", "")
            size_bytes = m.get("size", 0)
            size_gb = size_bytes / (1024**3)
            modified = m.get("modified_at", "")

            if size_gb >= 1:
                size_str = f"{size_gb:.1f} GB"
            else:
                size_mb = size_bytes / (1024**2)
                size_str = f"{size_mb:.0f} MB"

            print(f"  {name:<30s} {size_str:<12s} {modified}")

        print("\n  ✅ Ollama 模型已列出")

    except urllib.error.URLError:
        print("  ❌ Ollama 未运行")
        print("  💡 启动 Ollama: ollama serve")
    except Exception as e:
        print(f"  ❌ 扫描失败: {e}")

    print()


# ---------------------------------------------------------------------------
# 新增命令: elfie route show <elfie_id>
# ---------------------------------------------------------------------------


def cmd_route(args):
    subcmd = args.route_command

    if subcmd == "show":
        cmd_route_show(args)


def cmd_route_show(args):
    elfie_id = args.elfie_id

    print(f"\n  🗺️  {elfie_id} 场景路由\n")

    route = load_model_route(elfie_id)

    print(f"  {'场景':<10s} {'主模型':<30s} {'Fallback链':<30s} {'能量阈值':<8s}")
    print("  " + "-" * 85)

    for scene in SCENE_SLOTS:
        scene_route = route.scene_routes.get(scene)
        if not scene_route:
            continue

        primary = scene_route.primary

        fallbacks = scene_route.fallbacks
        if fallbacks:
            fallback_str = " → ".join(fallbacks)
        else:
            fallback_str = "(无)"

        threshold = f"{scene_route.energy_threshold}%"

        print(f"  {scene:<10s} {primary:<30s} {fallback_str:<30s} {threshold:<8s}")

    print()

def config_tui():
    while True:
        clear_screen()
        print_banner()
        config = load_config()
        
        print("  📋 配置菜单")
        print("  " + "=" * 45)
        print("  1. 查看当前配置")
        print("  2. 配置大模型 (LLM)")
        print("  3. 配置服务商 (Providers)")
        print("  4. 配置引擎参数")
        print("  5. 配置安全设置")
        print("  6. 配置精灵领养")
        print("  7. 测试配置")
        print("  8. 重置为默认配置")
        print("  0. 退出")
        print()
        
        try:
            choice = input("请选择 [0-8]: ").strip()
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
            config_providers(config)
        elif choice == "4":
            config_engine(config)
        elif choice == "5":
            config_security(config)
        elif choice == "6":
            config_adoption(config)
        elif choice == "7":
            test_config(config)
        elif choice == "8":
            reset_config()

def show_config(config):
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

    providers = config.get("providers", {})
    if providers:
        print("  【已配置服务商】")
        for provider_id, info in providers.items():
            profile = get_profile(provider_id)
            name = profile.name if profile else provider_id
            status = info.get("status", "inactive")
            status_icon = "✅" if status == "active" else "⭕"
            print(f"    {status_icon} {name}")
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
            providers = list(BUILTIN_PROFILES.keys())
            print("\n可用服务商:")
            for i, pid in enumerate(providers, 1):
                profile = BUILTIN_PROFILES[pid]
                print(f"  {i}. {pid:12s} - {profile.name}")
            try:
                idx = int(input("请选择 [1-{}]: ".format(len(providers)))) - 1
                if 0 <= idx < len(providers):
                    provider_id = providers[idx]
                    llm['default_cheap_provider'] = provider_id
                    llm['default_deep_provider'] = provider_id
            except:
                pass


def config_providers(config):
    while True:
        clear_screen()
        print_banner()
        print("  🔑 服务商配置")
        print("  " + "=" * 45)
        print()

        providers_config = config.get("providers", {})

        print("  【已配置服务商】")
        for provider_id, info in providers_config.items():
            profile = get_profile(provider_id)
            name = profile.name if profile else provider_id
            status = info.get("status", "inactive")
            status_icon = "✅" if status == "active" else "⭕"
            print(f"    {status_icon} {name}")
        print()

        print("  1. 配置服务商 (使用 elfie login)")
        print("  2. 测试服务商连通性")
        print("  3. 查看所有服务商")
        print("  0. 返回")
        print()

        try:
            choice = input("请选择 [0-3]: ").strip()
        except KeyboardInterrupt:
            return

        if choice == "0":
            break
        elif choice == "1":
            print("\n  可用服务商:")
            providers = list(BUILTIN_PROFILES.keys())
            for i, pid in enumerate(providers, 1):
                profile = BUILTIN_PROFILES[pid]
                print(f"    {i}. {pid:12s} - {profile.name}")

            try:
                idx = int(input("\n  请选择 [1-{}]: ".format(len(providers)))) - 1
                if 0 <= idx < len(providers):
                    provider_id = providers[idx]
                    login_args = argparse.Namespace(provider=provider_id)
                    cmd_login(login_args)
                    config = load_config()
            except:
                pass
        elif choice == "2":
            print("\n  测试所有已配置服务商...\n")
            rt_config = LLMRuntimeConfig.load()
            for provider_id in providers_config.keys():
                profile = get_profile(provider_id)
                if not profile:
                    continue

                result = verify_provider(provider_id, rt_config)
                name = profile.name

                if result["status"] == "active":
                    latency = result.get("latency_ms", 0)
                    print(f"    ✅ {name}: 可用 ({latency:.0f}ms)")
                else:
                    error = result.get("error", "未知错误")
                    print(f"    ❌ {name}: {error}")

            input("\n  按回车键继续...")
        elif choice == "3":
            cmd_providers_list()
            input("  按回车键继续...")


def config_engine(config):
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
    clear_screen()
    print_banner()
    print("  🧪 测试配置")
    print("  " + "=" * 45)
    print()

    print("  [1/3] 测试 Ollama 连接...")
    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
        if resp.status == 200:
            print("  ✅ Ollama 连接成功")
        else:
            print("  ❌ Ollama 响应异常")
    except:
        print("  ⚠️  Ollama 未运行（将使用 fallback 模式）")

    print("\n  [2/3] 测试数据库...")
    try:
        conn = sqlite3.connect(str(get_db_path()))
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

    providers_config = config.get("providers", {})
    if providers_config:
        print("\n  [4/4] 测试服务商连通性...")
        rt_config = LLMRuntimeConfig.load()
        for provider_id in providers_config.keys():
            profile = get_profile(provider_id)
            if not profile:
                continue

            result = verify_provider(provider_id, rt_config)
            name = profile.name

            if result["status"] == "active":
                latency = result.get("latency_ms", 0)
                print(f"    ✅ {name}: 可用 ({latency:.0f}ms)")
            else:
                print(f"    ❌ {name}: 不可用")

    print("\n✅ 测试完成")
    input("\n按回车键继续...")


def reset_config():
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


def cmd_status():
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
        conn = sqlite3.connect(str(get_db_path()))
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
    print("  🌐 启动服务并打开浏览器...")
    print()

    subprocess.Popen(
        [sys.executable, 'scripts/serve.py', '--fallback'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    time.sleep(3)

    url = "http://localhost:8000/static/login.html"
    print(f"  打开浏览器: {url}")
    webbrowser.open(url)

    print("  ✅ 服务已启动")
    print()


def cmd_stats():
    print("  📈 使用统计")
    print("  " + "=" * 45)
    print()
    
    try:
        conn = sqlite3.connect(str(get_db_path()))
        
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
    print("  👥 会话管理")
    print("  " + "=" * 45)
    print()

    try:
        conn = sqlite3.connect(str(get_db_path()))
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
    print("  🗄️  数据库工具")
    print("  " + "=" * 45)
    print()

    if hasattr(args, 'db_command') and args.db_command == 'backup':
        backup_path = str(get_db_path()) + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            import shutil
            shutil.copy(str(get_db_path()), backup_path)
            print(f"  ✅ 数据库已备份到: {backup_path}")
        except Exception as e:
            print(f"  ❌ 备份失败: {e}")
    elif hasattr(args, 'db_command') and args.db_command == 'reset':
        print("  ⚠️  这将删除所有数据，是否继续？")
        choice = input("输入 'yes' 确认: ").strip()
        if choice.lower() == 'yes':
            try:
                os.remove(str(get_db_path()))
                print("  ✅ 数据库已删除，重启服务将自动创建新数据库")
            except Exception as e:
                print(f"  ❌ 删除失败: {e}")
    else:
        print("  可用命令:")
        print("    elfie db backup  - 备份数据库")
        print("    elfie db reset   - 重置数据库")
        print()

        try:
            conn = sqlite3.connect(str(get_db_path()))

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
    print(f"  ElfieNest v{VERSION}")
    print()
    print("  🦊 仿生生命体系统")
    print("  一个基于三层大脑架构的 AI 生物模拟系统")
    print()

def cmd_setup():
    clear_screen()
    print_banner()
    print("  ✨ 欢迎使用 ElfieNest 设置向导")
    print("  " + "=" * 45)
    print()

    try:
        conn = sqlite3.connect(str(get_db_path()))
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

    print("  【步骤 1/4】创建管理员账号")
    print()
    username = input_text("  管理员用户名", "admin")
    password = input_text("  管理员密码", "admin123")
    print()

    print("  【步骤 2/4】配置大模型服务商")
    print()
    print("  检测 Ollama...")
    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
        print("  ✅ Ollama 已运行")
    except:
        print("  ⚠️  Ollama 未运行，将使用 fallback 模式")
    print()

    providers = list(BUILTIN_PROFILES.keys())
    print("  可用服务商:")
    for i, pid in enumerate(providers, 1):
        profile = BUILTIN_PROFILES[pid]
        print(f"    {i}. {pid:12s} - {profile.name}")
    print()

    print("  是否配置其他服务商？(y/N): ", end="")
    try:
        choice = input().strip().lower()
    except KeyboardInterrupt:
        choice = "n"

    if choice == "y":
        config = load_config()
        env_vars = load_env()

        while True:
            print("\n  选择要配置的服务商编号 (输入 0 跳过): ", end="")
            try:
                idx_str = input().strip()
                if idx_str == "0":
                    break

                idx = int(idx_str) - 1
                if 0 <= idx < len(providers):
                    provider_id = providers[idx]
                    profile = BUILTIN_PROFILES[provider_id]

                    if profile.api_key_env_var:
                        print(f"\n  配置 {profile.name}")
                        api_key = input_password("  API Key")
                        if api_key:
                            if "providers" not in config:
                                config["providers"] = {}
                            config["providers"][provider_id] = {
                                "api_base": profile.api_base,
                                "api_mode": profile.api_mode,
                                "status": "active",
                            }

                            env_vars[profile.api_key_env_var] = api_key

                            print("  ✅ 配置已保存")
                    else:
                        print(f"  {profile.name} 无需 API Key")
            except (ValueError, KeyboardInterrupt):
                break

        save_config(config)
        save_env(env_vars)

    print()
    print("  【步骤 3/4】初始化数据库")
    print()
    from elfienest.manage.store import init_db, migrate_db_if_needed, hash_password

    db_path = str(get_db_path())
    init_db(db_path)
    migrate_db_if_needed(db_path)

    conn = sqlite3.connect(db_path)
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
    print("  【步骤 4/4】完成设置")
    print()
    print("  " + "=" * 45)
    print("  ✅ 设置完成！")
    print()
    print("  启动服务: elfie")
    print(f"  登录信息: {username} / {password}")
    print()

def cmd_restart():
    print("  🔄 重启服务...")

    try:
        subprocess.run(['pkill', '-f', 'serve.py'], capture_output=True)
        print("  ✓ 已停止旧服务")
    except:
        pass

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
    print("  🛑 停止服务...")
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

    models_parser = subparsers.add_parser("models", help="模型管理")
    models_parser.add_argument(
        "models_command",
        nargs="?",
        choices=["list", "scan"],
        default="list",
        help="模型命令"
    )

    providers_parser = subparsers.add_parser("providers", help="管理服务商")
    providers_parser.add_argument(
        "providers_command",
        nargs="?",
        choices=["list", "test", "add", "remove"],
        default="list",
        help="服务商命令"
    )
    providers_parser.add_argument("provider_id", nargs="?", help="服务商标识")

    login_parser = subparsers.add_parser("login", help="配置服务商 API Key")
    login_parser.add_argument("provider", help="服务商标识 (如 openai, deepseek)")

    route_parser = subparsers.add_parser("route", help="模型路由管理")
    route_parser.add_argument("route_command", choices=["show"], help="路由命令")
    route_parser.add_argument("elfie_id", nargs="?", help="精灵 ID")

    subparsers.add_parser("status", help="查看服务状态")
    subparsers.add_parser("web", help="启动服务并打开浏览器")
    subparsers.add_parser("stats", help="显示使用统计")
    subparsers.add_parser("session", help="管理会话")
    subparsers.add_parser("logs", help="查看日志")
    subparsers.add_parser("version", help="显示版本")
    subparsers.add_parser("setup", help="首次设置向导")
    subparsers.add_parser("restart", help="重启服务")
    subparsers.add_parser("stop", help="停止服务")

    db_parser = subparsers.add_parser("db", help="数据库工具")
    db_parser.add_argument("db_command", nargs="?", choices=["backup", "reset"], help="数据库命令")

    args = parser.parse_args()

    if args.command == "config":
        config_tui()
    elif args.command == "models":
        cmd_models(args)
    elif args.command == "providers":
        cmd_providers(args)
    elif args.command == "login":
        cmd_login(args)
    elif args.command == "route":
        cmd_route(args)
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
