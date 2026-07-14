from __future__ import annotations

import sqlite3
import urllib.error
import urllib.request
from typing import Final

from elfienest.cli.tui.common import clear_screen, print_banner
from elfienest.config.provider_service import list_configured_provider_rows
from elfienest.config.user_config import UserConfig, read_user_config, write_user_config
from elfienest.operations.service import DatabaseUnavailableError, collect_usage_stats
from runtime.config import LLMRuntimeConfig
from runtime.models.catalog import verify_provider
from runtime.providers.profiles import get_profile
from runtime.storage.data_home import get_config_path

CONFIG_FILE: Final = str(get_config_path())


def show_config(config: UserConfig) -> None:
    clear_screen()
    print_banner()
    print("  📄 当前配置")
    print("  " + "=" * 45)
    print()

    print("  【大模型与粮食策略】")
    print("    统一由 Runtime Lab 管理：.venv/bin/python -m runtime.lab")
    print("    精灵只选择默认/允许/兜底粮食，不直接绑定模型")
    print()

    if config.get("providers", {}):
        print("  【已配置服务商】")
        for row in list_configured_provider_rows(config):
            status_icon = "✅" if row.status == "active" else "⭕"
            print(f"    {status_icon} {row.name}")
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


def test_config(config: UserConfig) -> None:
    clear_screen()
    print_banner()
    print("  🧪 测试配置")
    print("  " + "=" * 45)
    print()

    print("  [1/3] 测试 Ollama 连接...")
    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
    except (OSError, TimeoutError, urllib.error.URLError):
        print("  ⚠️  Ollama 未运行（将使用 fallback 模式）")
    else:
        if resp.status == 200:
            print("  ✅ Ollama 连接成功")
        else:
            print("  ❌ Ollama 响应异常")

    print("\n  [2/3] 测试数据库...")
    try:
        stats = collect_usage_stats()
        print(f"  ✅ 数据库正常（{stats.user_count} 个用户）")
    except (DatabaseUnavailableError, OSError, sqlite3.Error) as e:
        print(f"  ❌ 数据库错误: {e}")

    print("\n  [3/3] 测试配置文件...")
    if read_user_config():
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


def reset_config() -> None:
    print("\n⚠️  这将重置所有配置为默认值，是否继续？")
    choice = input("输入 'yes' 确认: ").strip()
    if choice.lower() == "yes":
        default_config = {
            "system": {
                "engine": {
                    "tick_interval_sec": 1.5,
                    "tts_enabled": True,
                    "max_elfies_per_room": 10,
                },
                "security": {"session_ttl_hours": 24, "rate_limit_per_minute": 60},
                "adoption": {
                    "max_elfies_per_user": 3,
                    "default_personality_style": "活泼好动",
                },
            }
        }
        write_user_config(default_config)
        print("✅ 配置已重置")
    else:
        print("已取消")
    input("\n按回车键继续...")
