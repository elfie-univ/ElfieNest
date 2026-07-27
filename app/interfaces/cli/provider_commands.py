from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.interfaces.cli.tui.common import input_password, input_text
from app.features.configuration.provider_service import (
    CUSTOM_OPENAI_PROVIDER_ID,
    get_known_profile,
    list_provider_rows,
    remove_provider_credentials,
    save_provider_credentials,
)
from app.features.configuration.user_config import (
    read_env_file,
    read_user_config,
    write_env_file,
    write_user_config,
)
from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.models.catalog import verify_provider
from ai_runtime.providers.profiles import BUILTIN_PROFILES, ProviderProfile, get_profile


@dataclass(frozen=True)
class ProviderLoginInput:
    display_name: str
    api_key: str
    base_url: str
    test_model: str


def login_provider(provider_id: str) -> None:
    profile = get_known_profile(provider_id)
    if not profile:
        _print_unknown_provider(provider_id)
        return

    login_input = _prompt_login_input(provider_id, profile)
    if login_input is None:
        return

    print("\n  ⏳ Verifying connectivity...")

    temp_config = LLMRuntimeConfig()
    temp_config.providers[provider_id] = {
        "api_key": login_input.api_key,
        "api_base": login_input.base_url,
        "api_mode": profile.api_mode,
        "status": "inactive",
    }
    if login_input.test_model:
        temp_config.providers[provider_id]["test_model"] = login_input.test_model

    result = verify_provider(provider_id, temp_config)
    if result["status"] != "active":
        error = result.get("error", "unknown error")
        print(f"  ⚠️  Connectivity verification failed: {error}")
        print("  Config will still be saved. Test again later with: elfienest providers test\n")
    else:
        latency = result.get("latency_ms", 0)
        print(f"  ✅ Connectivity verified! Latency: {latency:.0f}ms\n")

    save_result = save_provider_credentials(
        read_user_config(),
        read_env_file(),
        provider_id,
        login_input.api_key,
        login_input.base_url,
        display_name=login_input.display_name,
        test_model=login_input.test_model,
    )
    if save_result is None:
        _print_unknown_provider(provider_id)
        return
    write_user_config(save_result.config)
    write_env_file(save_result.env_vars)

    saved_name = login_input.display_name or profile.name
    print(f"  ✅ {saved_name} configuration saved")


def _prompt_login_input(
    provider_id: str,
    profile: ProviderProfile,
) -> ProviderLoginInput | None:
    print(f"\n🔑 Configure {profile.name} provider\n")

    if provider_id == CUSTOM_OPENAI_PROVIDER_ID:
        return _prompt_custom_openai_login()
    return _prompt_builtin_provider_login(profile)


def _prompt_custom_openai_login() -> ProviderLoginInput | None:
    display_name = (input_text("  Name") or "").strip()
    if not display_name:
        print("❌ Name cannot be empty")
        return None

    base_url = (input_text("  Endpoint / Base URL") or "").strip()
    if not base_url:
        print("❌ Endpoint / Base URL cannot be empty")
        return None

    test_model = (input_text("  Test model") or "").strip()
    if not test_model:
        print("❌ Test model cannot be empty")
        return None

    api_key = input_password("  API Key") or ""
    if not api_key:
        print("❌ API Key cannot be empty")
        return None

    return ProviderLoginInput(
        display_name=display_name,
        api_key=api_key,
        base_url=base_url,
        test_model=test_model,
    )


def _prompt_builtin_provider_login(
    profile: ProviderProfile,
) -> ProviderLoginInput | None:
    api_key = ""
    if profile.api_key_env_var:
        api_key = input_password("  API Key") or ""
        if not api_key:
            print("❌ API Key cannot be empty")
            return None
    else:
        print("  ℹ️  Ollama doesn't require API Key, skipping")

    base_url_hint = f"Press Enter for default {profile.api_base}"
    base_url_input = (input_text(f"  Base URL ({base_url_hint})") or "").strip()
    base_url = base_url_input if base_url_input else profile.api_base
    return ProviderLoginInput(
        display_name="",
        api_key=api_key,
        base_url=base_url,
        test_model="",
    )


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
    print("\n  📋 Provider List\n")

    config = read_user_config()

    print(f"  {'ID':<12s} {'Name':<20s} {'Status':<8s} {'API Mode':<20s}")
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
        print(f"❌ Unknown provider: {provider_id}")
        return

    name = _configured_provider_name(provider_id, profile.name)
    print(f"\n  ⏳ Testing {name} connectivity...\n")

    config = LLMRuntimeConfig.load()
    result = verify_provider(provider_id, config)

    if result["status"] == "active":
        latency = result.get("latency_ms", 0)
        print(f"  ✅ {name} available, latency: {latency:.0f}ms")
    else:
        error = result.get("error", "unknown error")
        print(f"  ❌ {name} unavailable: {error}")

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
        print(f"❌ Unknown provider: {provider_id}")
        return

    name = _configured_provider_name(provider_id, remove_result.profile.name)
    if remove_result.removed_config:
        write_user_config(remove_result.config)
        print(f"  ✅ Removed {name} from config.yaml")

    if remove_result.removed_env_key or remove_result.removed_base_url_env_key:
        write_env_file(remove_result.env_vars)

    if remove_result.removed_env_key:
        print(f"  ✅ Removed {remove_result.profile.api_key_env_var} from .env")
    if remove_result.removed_base_url_env_key:
        print(f"  ✅ Removed {remove_result.profile.base_url_env_var} from .env")

    print(f"\n  ✅ {name} configuration removed")


def _configured_provider_name(provider_id: str, fallback_name: str) -> str:
    rows = {row.provider_id: row for row in list_provider_rows(read_user_config())}
    return rows[provider_id].name if provider_id in rows else fallback_name


def _print_unknown_provider(provider_id: str) -> None:
    print(f"❌ Unknown provider: {provider_id}")
    print("\nAvailable providers:")
    for pid, profile in BUILTIN_PROFILES.items():
        print(f"  • {pid:12s} - {profile.name}")
