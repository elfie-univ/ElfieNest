from __future__ import annotations

from typing import Optional

from elfienest.cli.tui.common import input_password, input_text
from elfienest.config.provider_service import (
    get_known_profile,
    list_provider_rows,
    remove_provider_credentials,
    save_provider_credentials,
)
from elfienest.config.user_config import (
    read_env_file,
    read_user_config,
    write_env_file,
    write_user_config,
)
from runtime.config import LLMRuntimeConfig
from runtime.model_catalog import verify_provider
from runtime.provider_profiles import BUILTIN_PROFILES, get_profile


def login_provider(provider_id: str) -> None:
    profile = get_known_profile(provider_id)
    if not profile:
        _print_unknown_provider(provider_id)
        return

    print(f"\n🔑 配置 {profile.name} 服务商\n")

    api_key = ""
    if profile.api_key_env_var:
        api_key = input_password("  API Key") or ""
        if not api_key:
            print("❌ API Key 不能为空")
            return
    else:
        print("  ℹ️  Ollama 无需 API Key，跳过")

    base_url_hint = f"回车使用默认 {profile.api_base}"
    base_url_input = input_text(f"  Base URL ({base_url_hint})")
    base_url = base_url_input if base_url_input else profile.api_base

    print("\n  ⏳ 验证连通性...")

    temp_config = LLMRuntimeConfig()
    temp_config.providers[provider_id] = {
        "api_key": api_key,
        "api_base": base_url,
        "api_mode": profile.api_mode,
        "status": "inactive",
    }

    result = verify_provider(provider_id, temp_config)
    if result["status"] != "active":
        error = result.get("error", "未知错误")
        print(f"  ❌ 连通性验证失败: {error}")
        print("\n  请检查:")
        print("    • API Key 是否正确")
        print("    • Base URL 是否可访问")
        print("    • 网络连接是否正常")
        return

    latency = result.get("latency_ms", 0)
    print(f"  ✅ 连通性验证成功！延迟: {latency:.0f}ms\n")

    save_result = save_provider_credentials(
        read_user_config(),
        read_env_file(),
        provider_id,
        api_key,
        base_url,
    )
    if save_result is None:
        _print_unknown_provider(provider_id)
        return
    write_user_config(save_result.config)
    write_env_file(save_result.env_vars)

    print(f"  ✅ {profile.name} 配置已保存")


def dispatch_providers(subcmd: Optional[str], provider_id: Optional[str]) -> None:
    command = subcmd or "list"
    if command == "list":
        list_providers()
    elif command == "test" and provider_id:
        test_provider(provider_id)
    elif command == "add" and provider_id:
        add_provider(provider_id)
    elif command == "remove" and provider_id:
        remove_provider(provider_id)


def list_providers() -> None:
    print("\n  📋 服务商列表\n")

    config = read_user_config()

    print(f"  {'ID':<12s} {'名称':<20s} {'状态':<8s} {'API模式':<20s}")
    print("  " + "-" * 70)

    for row in list_provider_rows(config):
        status_icon = "✅" if row.status == "active" else "⭕"
        status_text = f"{status_icon} {row.status}"
        print(
            f"  {row.provider_id:<12s} {row.name:<20s} {status_text:<8s} {row.api_mode:<20s}"
        )

    print()


def test_provider(provider_id: str) -> None:
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


def add_provider(provider_id: str) -> None:
    profile = get_profile(provider_id)
    if not profile:
        _print_unknown_provider(provider_id)
        return

    login_provider(provider_id)


def remove_provider(provider_id: str) -> None:
    remove_result = remove_provider_credentials(
        read_user_config(),
        read_env_file(),
        provider_id,
    )
    if remove_result is None:
        print(f"❌ 未知服务商: {provider_id}")
        return

    if remove_result.removed_config:
        write_user_config(remove_result.config)
        print(f"  ✅ 已从 config.yaml 移除 {remove_result.profile.name}")

    if remove_result.removed_env_key:
        write_env_file(remove_result.env_vars)
        print(f"  ✅ 已从 .env 移除 {remove_result.profile.api_key_env_var}")

    print(f"\n  ✅ {remove_result.profile.name} 配置已移除")


def _print_unknown_provider(provider_id: str) -> None:
    print(f"❌ 未知服务商: {provider_id}")
    print("\n可用服务商:")
    for pid, profile in BUILTIN_PROFILES.items():
        print(f"  • {pid:12s} - {profile.name}")
