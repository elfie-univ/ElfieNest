from __future__ import annotations

from typing import Callable

from elfienest.cli.tui.common import clear_screen, print_banner
from elfienest.config.provider_service import (
    list_configured_provider_rows,
    list_provider_rows,
)
from elfienest.config.user_config import UserConfig, read_user_config
from runtime.config import LLMRuntimeConfig
from runtime.model_catalog import verify_provider
from runtime.provider_profiles import BUILTIN_PROFILES, get_profile

ProviderLogin = Callable[[str], None]


def config_providers(config: UserConfig, provider_login: ProviderLogin) -> None:
    while True:
        clear_screen()
        print_banner()
        print("  🔑 服务商配置")
        print("  " + "=" * 45)
        print()

        print("  【已配置服务商】")
        for row in list_configured_provider_rows(config):
            status_icon = "✅" if row.status == "active" else "⭕"
            print(f"    {status_icon} {row.name}")
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
        if choice == "1":
            _prompt_provider_login(provider_login)
            config = read_user_config()
        elif choice == "2":
            _test_configured_providers(config)
        elif choice == "3":
            _print_all_providers(read_user_config())
            input("  按回车键继续...")


def _prompt_provider_login(provider_login: ProviderLogin) -> None:
    print("\n  可用服务商:")
    providers = list(BUILTIN_PROFILES.keys())
    for i, pid in enumerate(providers, 1):
        profile = BUILTIN_PROFILES[pid]
        print(f"    {i}. {pid:12s} - {profile.name}")

    try:
        idx = int(input(f"\n  请选择 [1-{len(providers)}]: ")) - 1
    except (KeyboardInterrupt, ValueError):
        return
    if 0 <= idx < len(providers):
        provider_login(providers[idx])


def _test_configured_providers(config: UserConfig) -> None:
    print("\n  测试所有已配置服务商...\n")
    rt_config = LLMRuntimeConfig.load()
    providers_config = config.get("providers", {})
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


def _print_all_providers(config: UserConfig) -> None:
    print("\n  📋 服务商列表\n")
    print(f"  {'ID':<12s} {'名称':<20s} {'状态':<8s} {'API模式':<20s}")
    print("  " + "-" * 70)
    for row in list_provider_rows(config):
        status_icon = "✅" if row.status == "active" else "⭕"
        status_text = f"{status_icon} {row.status}"
        print(
            f"  {row.provider_id:<12s} {row.name:<20s} {status_text:<8s} {row.api_mode:<20s}"
        )
    print()
