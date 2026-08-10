from __future__ import annotations

import asyncio

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    GetElfieSettingsQuery,
    GetRuntimeSettingsQuery,
    GetSecuritySettingsQuery,
    InspectLocalProviderQuery,
    ProvidersError,
    ProvidersService,
    ResetSettingsCommand,
    SettingsError,
    SettingsService,
    VerifyProviderConnectionCommand,
)
from app.features.operations import (
    GetUsageStatsQuery,
    OperationsError,
    OperationsFacade,
)
from app.interfaces.cli.provider_projection import (
    configured_provider_rows,
    connections,
)
from app.interfaces.cli.tui.common import clear_screen, print_banner


def show_config(
    providers: ProvidersService,
    settings: SettingsService,
    principal: AccountPrincipal,
) -> None:
    clear_screen()
    print_banner()
    print("  📄 Current Configuration")
    print("  " + "=" * 45)
    print()

    print("  【LLM and Food Strategy】")
    print("    Managed by Runtime Lab: .venv/bin/python -m ai_runtime.lab")
    print("    Elfies choose default/allowed/fallback food, not direct model binding")
    print()

    configured = configured_provider_rows(providers, principal)
    if configured:
        print("  【Configured Providers】")
        for row in configured:
            print(f"    ✅ {row.name}")
        print()

    runtime = settings.get_runtime_settings(principal, GetRuntimeSettingsQuery())
    print("  【Engine Config】")
    print(f"    Tick interval: {runtime.tick_interval_sec}s")
    print()

    security = settings.get_security_settings(principal, GetSecuritySettingsQuery())
    print("  【Security Config】")
    print(f"    Session TTL: {security.session_ttl_days} days")
    print(f"    Max login attempts: {security.rate_limit.max_attempts}")
    print(f"    Rate limit window: {security.rate_limit.window_seconds}s")
    print()

    adoption = settings.get_elfie_settings(principal, GetElfieSettingsQuery())
    print("  【Adoption Config】")
    print(f"    Max elfies per user: {adoption.max_elfies_per_user}")
    print("    Allowed species: " + ", ".join(adoption.allowed_species_ids))
    enabled = tuple(
        name for name, is_enabled in adoption.personality_presets_enabled if is_enabled
    )
    print(f"    Enabled personality presets: {', '.join(enabled) or 'default'}")
    print()
    _pause()


def test_config(
    providers: ProvidersService,
    settings: SettingsService,
    operations: OperationsFacade,
    principal: AccountPrincipal,
) -> None:
    clear_screen()
    print_banner()
    print("  🧪 Testing Configuration")
    print("  " + "=" * 45)
    print()

    print("  [1/3] Testing Ollama connection...")
    try:
        local = providers.inspect_local_provider(principal, InspectLocalProviderQuery())
    except ProvidersError:
        print("  ⚠️  Ollama not running (will use fallback mode)")
    else:
        if local.state == "healthy":
            print("  ✅ Ollama connection successful")
        else:
            print("  ⚠️  Ollama not running (will use fallback mode)")

    print("\n  [2/3] Testing database...")
    try:
        stats = operations.get_usage_stats(GetUsageStatsQuery())
        print(f"  ✅ Database OK ({stats.user_count} users)")
    except (OperationsError, OSError) as error:
        print(f"  ❌ Database error: {error}")

    print("\n  [3/3] Testing config file...")
    try:
        settings.get_runtime_settings(principal, GetRuntimeSettingsQuery())
    except SettingsError as error:
        print(f"  ❌ Config error: {error}")
    else:
        print("  ✅ Config settings accessible")

    configured = tuple(
        item
        for item in connections(providers, principal)
        if item.enabled and not item.archived
    )
    if configured:
        print("\n  [4/4] Testing provider connectivity...")
        for connection in configured:
            try:
                result = asyncio.run(
                    providers.verify_connection(
                        principal,
                        VerifyProviderConnectionCommand(connection.connection_id),
                    )
                ).verification
            except ProvidersError:
                print(f"    ❌ {connection.alias}: unavailable")
                continue
            if result.status == "passed":
                print(
                    f"    ✅ {connection.alias}: available ({result.latency_ms or 0:.0f}ms)"
                )
            else:
                print(f"    ❌ {connection.alias}: unavailable")

    print("\n✅ Tests completed")
    _pause()


def reset_config(
    settings: SettingsService,
    principal: AccountPrincipal,
) -> None:
    print(
        "\n⚠️  This will reset app config to defaults. Provider and account data will be kept. Continue?"
    )
    try:
        choice = input("Type 'yes' to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if choice.lower() == "yes":
        settings.reset_settings(principal, ResetSettingsCommand())
        print("✅ Config reset")
    else:
        print("Cancelled")
    _pause()


def _pause() -> None:
    try:
        input("\nPress Enter to continue...")
    except (EOFError, KeyboardInterrupt):
        return


__all__ = ("reset_config", "show_config", "test_config")
