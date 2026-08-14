from __future__ import annotations

from typing import MutableMapping

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    GetElfieSettingsQuery,
    GetRuntimeSettingsQuery,
    GetSecuritySettingsQuery,
    LoginRateLimit,
    SettingsService,
    UpdateElfieSettingsCommand,
    UpdateRuntimeSettingsCommand,
    UpdateSecuritySettingsCommand,
)
from app.interfaces.cli.tui.common import clear_screen, print_banner
from app.interfaces.cli.tui.menu import MenuItem, TerminalMenuPort


def config_llm(config: object | None = None) -> None:
    _ = config
    clear_screen()
    print_banner()
    print("  🤖 LLM and Food Strategy")
    print("  " + "=" * 45)
    print()
    print(
        "  Provider connections, models and food packages are managed in Config Center."
    )
    try:
        input("Press Enter to return...")
    except (EOFError, KeyboardInterrupt):
        return


def config_engine(
    settings: SettingsService,
    principal: AccountPrincipal,
    menu: TerminalMenuPort,
) -> None:
    while True:
        current = settings.get_runtime_settings(principal, GetRuntimeSettingsQuery())
        choice = menu.choose(
            "Engine Parameters",
            (MenuItem("1", f"Tick interval (sec): {current.tick_interval_sec}"),),
            breadcrumb="ElfieNest / Config / App / Engine",
            back_label="Save and return",
        )
        if choice is None:
            return
        if choice == "1":
            value = _read_float(
                menu,
                "Enter tick interval (sec)",
                current.tick_interval_sec,
                minimum=0.01,
            )
            if value is not None:
                settings.update_runtime_settings(
                    principal,
                    UpdateRuntimeSettingsCommand(tick_interval_sec=value),
                )


def config_security(
    settings: SettingsService,
    principal: AccountPrincipal,
    menu: TerminalMenuPort,
) -> None:
    while True:
        current = settings.get_security_settings(principal, GetSecuritySettingsQuery())
        choice = menu.choose(
            "Session and Security",
            (
                MenuItem("1", f"Session TTL (days): {current.session_ttl_days}"),
                MenuItem("2", f"Max login attempts: {current.rate_limit.max_attempts}"),
                MenuItem(
                    "3",
                    f"Rate limit window (sec): {current.rate_limit.window_seconds}",
                ),
            ),
            breadcrumb="ElfieNest / Config / Owner and Security",
            back_label="Save and return",
        )
        if choice is None:
            return
        if choice == "1":
            value = _read_int(
                menu,
                "Enter session TTL (days)",
                current.session_ttl_days,
                minimum=1,
                maximum=90,
            )
            if value is not None:
                settings.update_security_settings(
                    principal,
                    UpdateSecuritySettingsCommand(session_ttl_days=value),
                )
        elif choice in {"2", "3"}:
            is_attempts = choice == "2"
            value = _read_int(
                menu,
                (
                    "Enter max failed attempts in window"
                    if is_attempts
                    else "Enter rate limit window (sec)"
                ),
                (
                    current.rate_limit.max_attempts
                    if is_attempts
                    else current.rate_limit.window_seconds
                ),
                minimum=1,
                maximum=100 if is_attempts else 3600,
            )
            if value is not None:
                settings.update_security_settings(
                    principal,
                    UpdateSecuritySettingsCommand(
                        rate_limit=LoginRateLimit(
                            max_attempts=(
                                value
                                if is_attempts
                                else current.rate_limit.max_attempts
                            ),
                            window_seconds=(
                                current.rate_limit.window_seconds
                                if is_attempts
                                else value
                            ),
                        )
                    ),
                )


def config_adoption(
    settings: SettingsService,
    principal: AccountPrincipal,
    menu: TerminalMenuPort,
) -> None:
    while True:
        current = settings.get_elfie_settings(principal, GetElfieSettingsQuery())
        enabled = dict(current.personality_presets_enabled)
        if not enabled:
            enabled.update(dict.fromkeys(_PERSONALITY_PRESETS, True))
        choice = menu.choose(
            "Elfie Adoption",
            (
                MenuItem("1", f"Max elfies per user: {current.max_elfies_per_user}"),
                MenuItem("2", "Personality preset toggles"),
            ),
            breadcrumb="ElfieNest / Config / App / Elfie Adoption",
            back_label="Save and return",
        )
        if choice is None:
            return
        if choice == "1":
            value = _read_int(
                menu,
                "Enter max elfies per user",
                current.max_elfies_per_user,
                minimum=1,
                maximum=32,
            )
            if value is not None:
                settings.update_elfie_settings(
                    principal,
                    UpdateElfieSettingsCommand(max_elfies_per_user=value),
                )
        elif choice == "2" and _toggle_personality_menu(menu, enabled):
            settings.update_elfie_settings(
                principal,
                UpdateElfieSettingsCommand(
                    personality_presets_enabled=tuple(enabled.items())
                ),
            )


_PERSONALITY_PRESETS = ("Energetic", "Calm", "Curious", "Timid", "Tsundere", "Random")


def _toggle_personality_menu(
    menu: TerminalMenuPort,
    enabled: MutableMapping[str, bool],
) -> bool:
    changed = False
    while True:
        choice = menu.choose(
            "Personality Preset Toggles",
            tuple(
                MenuItem(
                    str(index),
                    f"{name}: {'enabled' if enabled.get(name, True) else 'disabled'}",
                )
                for index, name in enumerate(_PERSONALITY_PRESETS, 1)
            ),
            breadcrumb="ElfieNest / Config / App / Elfie Adoption / Personality",
            back_label="Back to adoption config",
        )
        if choice is None:
            return changed
        if not choice.isdigit() or not 1 <= int(choice) <= len(_PERSONALITY_PRESETS):
            continue
        name = _PERSONALITY_PRESETS[int(choice) - 1]
        if sum(bool(value) for value in enabled.values()) == 1 and enabled.get(
            name, True
        ):
            continue
        enabled[name] = not enabled.get(name, True)
        changed = True


def _read_float(
    menu: TerminalMenuPort,
    prompt: str,
    current: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    try:
        raw = menu.read_text(f"{prompt} [{current}]: ", default=str(current))
        if raw is None:
            return None
        value = float(raw)
        if minimum is not None and value < minimum:
            raise ValueError
        if maximum is not None and value > maximum:
            raise ValueError
        return value
    except (TypeError, ValueError):
        print("❌ Invalid input")
        return None


def _read_int(
    menu: TerminalMenuPort,
    prompt: str,
    current: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    try:
        raw = menu.read_text(f"{prompt} [{current}]: ", default=str(current))
        if raw is None:
            return None
        value = int(raw)
        if minimum is not None and value < minimum:
            raise ValueError
        if maximum is not None and value > maximum:
            raise ValueError
        return value
    except (TypeError, ValueError):
        print("❌ Invalid input")
        return None


__all__ = ("config_adoption", "config_engine", "config_llm", "config_security")
