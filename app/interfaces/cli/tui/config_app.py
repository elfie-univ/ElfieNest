from __future__ import annotations

from typing import Callable, Optional

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    CapabilitiesService,
    ProvidersService,
    SettingsService,
)
from app.features.configuration import food as food_feature
from app.interfaces.cli.tui.capability_menu import config_capabilities
from app.interfaces.cli.tui.common import clear_screen, print_banner, print_tui_panel
from app.interfaces.cli.tui.config_views import reset_config, show_config
from app.interfaces.cli.tui.food_menu import config_food
from app.interfaces.cli.tui.menu import MenuItem, TerminalMenuPort
from app.interfaces.cli.tui.provider_menu import config_providers

ProviderLogin = Callable[[str], None]


def run_config_tui(
    providers: ProvidersService,
    food: food_feature.FoodService,
    capabilities: CapabilitiesService,
    settings: SettingsService,
    principal: AccountPrincipal,
    provider_login: ProviderLogin,
    menu: TerminalMenuPort,
    initial_path: Optional[str] = None,
) -> None:
    """Run the Config menu over injected public Feature facades."""
    if initial_path:
        _dispatch_initial_path(
            initial_path,
            providers,
            food,
            capabilities,
            principal,
            provider_login,
            menu,
        )
    while True:
        clear_screen()
        print_banner()
        print_tui_panel(
            "Config Center / Application Config",
            "Provider, model, Food and tool configuration; other settings in Web console",
        )
        choice = menu.choose(
            "Config Center",
            (
                MenuItem("1", "Provider and Model Configuration"),
                MenuItem("2", "Agent Capability Validation"),
                MenuItem("3", "Food Strategy Configuration"),
                MenuItem("4", "View Current Config"),
                MenuItem("5", "Reset Application Config"),
            ),
            breadcrumb="ElfieNest / Config",
            back_label="Back to Home",
        )
        if choice is None:
            print("\nGoodbye!")
            return
        if choice == "1":
            config_providers(providers, principal, provider_login, menu)
        elif choice == "2":
            config_capabilities(capabilities, principal, menu)
        elif choice == "3":
            config_food(food, providers, principal, menu)
        elif choice == "4":
            show_config(providers, settings, principal)
        elif choice == "5":
            reset_config(settings, principal)


def _dispatch_initial_path(
    initial_path: str,
    providers: ProvidersService,
    food: food_feature.FoodService,
    capabilities: CapabilitiesService,
    principal: AccountPrincipal,
    provider_login: ProviderLogin,
    menu: TerminalMenuPort,
) -> None:
    path = initial_path.strip().lower()
    if path in {"provider", "providers"}:
        config_providers(providers, principal, provider_login, menu)
    elif path in {"agent", "tools"}:
        config_capabilities(capabilities, principal, menu)
    elif path in {"food", "foods"}:
        config_food(food, providers, principal, menu)
    elif path == "login":
        provider_login("ollama")


__all__ = ("ProviderLogin", "run_config_tui")
