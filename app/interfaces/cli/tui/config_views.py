from __future__ import annotations

import copy
import urllib.error
import urllib.request
from typing import Final

from ai_runtime.config import DEFAULT_SYSTEM_SETTINGS, LLMRuntimeConfig
from ai_runtime.models.catalog import verify_provider
from ai_runtime.providers.profiles import get_profile
from ai_runtime.storage.data_home import get_config_path
from app.features.configuration.provider_service import list_configured_provider_rows
from app.features.configuration.user_config import (
    UserConfig,
    read_user_config,
    write_user_config,
)
from app.features.operations import (
    GetUsageStatsQuery,
    OperationsError,
    OperationsFacade,
)
from app.interfaces.cli.tui.common import clear_screen, print_banner

CONFIG_FILE: Final = str(get_config_path())


def show_config(config: UserConfig) -> None:
    clear_screen()
    print_banner()
    print("  📄 Current Configuration")
    print("  " + "=" * 45)
    print()

    print("  【LLM and Food Strategy】")
    print("    Managed by Runtime Lab: .venv/bin/python -m ai_runtime.lab")
    print("    Elfies choose default/allowed/fallback food, not direct model binding")
    print()

    if config.get("providers", {}):
        print("  【Configured Providers】")
        for row in list_configured_provider_rows(config):
            status_icon = "✅" if row.status == "active" else "⭕"
            print(f"    {status_icon} {row.name}")
        print()

    engine = config.get("system", {}).get("engine", {})
    print("  【Engine Config】")
    print(f"    Tick interval: {engine.get('tick_interval_sec', 1.5)}s")
    print()

    security = config.get("system", {}).get("security", {})
    rate_limit = security.get("rate_limit", {})
    print("  【Security Config】")
    print(f"    Session TTL: {security.get('session_ttl_days', 7)} days")
    print(f"    Max login attempts: {rate_limit.get('max_attempts', 5)}")
    print(f"    Rate limit window: {rate_limit.get('window_seconds', 300)}s")
    print()

    adoption = config.get("system", {}).get("adoption", {})
    print("  【Adoption Config】")
    print(f"    Max elfies per user: {adoption.get('max_elfies_per_user', 3)}")
    print(
        "    Allowed species: "
        + ", ".join(adoption.get("allowed_species_ids", ["dog", "fox"]))
    )
    enabled = adoption.get("personality_presets_enabled", {})
    enabled_names = [name for name, is_enabled in enabled.items() if is_enabled]
    print(f"    Enabled personality presets: {', '.join(enabled_names) or 'default'}")
    print()

    _pause()


def test_config(config: UserConfig, operations: OperationsFacade) -> None:
    clear_screen()
    print_banner()
    print("  🧪 Testing Configuration")
    print("  " + "=" * 45)
    print()

    print("  [1/3] Testing Ollama connection...")
    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
    except (OSError, TimeoutError, urllib.error.URLError):
        print("  ⚠️  Ollama not running (will use fallback mode)")
    else:
        if resp.status == 200:
            print("  ✅ Ollama connection successful")
        else:
            print("  ❌ Ollama response abnormal")

    print("\n  [2/3] Testing database...")
    try:
        stats = operations.get_usage_stats(GetUsageStatsQuery())
        print(f"  ✅ Database OK ({stats.user_count} users)")
    except (OperationsError, OSError) as e:
        print(f"  ❌ Database error: {e}")

    print("\n  [3/3] Testing config file...")
    if read_user_config():
        print(f"  ✅ Config file exists: {CONFIG_FILE}")
    else:
        print("  ⚠️  Config file missing (will use defaults)")

    providers_config = config.get("providers", {})
    if providers_config:
        print("\n  [4/4] Testing provider connectivity...")
        rt_config = LLMRuntimeConfig.load()
        for provider_id in providers_config.keys():
            profile = get_profile(provider_id)
            if not profile:
                continue

            result = verify_provider(provider_id, rt_config)
            name = profile.name

            if result["status"] == "active":
                latency = result.get("latency_ms", 0)
                print(f"    ✅ {name}: available ({latency:.0f}ms)")
            else:
                print(f"    ❌ {name}: unavailable")

    print("\n✅ Tests completed")
    _pause()


def reset_config() -> None:
    print(
        "\n⚠️  This will reset app config to defaults. Provider and account data will be kept. Continue?"
    )
    try:
        choice = input("Type 'yes' to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if choice.lower() == "yes":
        updated = copy.deepcopy(read_user_config())
        updated["system"] = copy.deepcopy(DEFAULT_SYSTEM_SETTINGS)
        write_user_config(updated)
        print("✅ Config reset")
    else:
        print("Cancelled")
    _pause()


def _pause() -> None:
    """Wait for user to return; exit silently when input is redirected."""
    try:
        input("\nPress Enter to continue...")
    except (EOFError, KeyboardInterrupt):
        return
