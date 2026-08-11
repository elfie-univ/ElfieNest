from __future__ import annotations

from typing import Callable, Optional, Protocol

from app.features.accounts import AccountPrincipal
from app.features.configuration import ProvidersService, SettingsService
from app.interfaces.cli.tui.common import clear_screen, print_banner, print_tui_panel
from app.interfaces.cli.tui.config_views import reset_config, show_config
from app.interfaces.cli.tui.menu import MenuItem, TerminalMenuPort
from app.interfaces.cli.tui.provider_menu import config_providers

ProviderLogin = Callable[[str], None]


class RuntimeConfigMenus(Protocol):
    def tool_menu(self) -> None: ...

    def food_menu(self) -> None: ...


def run_config_tui(
    providers: ProvidersService,
    settings: SettingsService,
    principal: AccountPrincipal,
    provider_login: ProviderLogin,
    runtime_menus: RuntimeConfigMenus,
    menu: TerminalMenuPort,
    initial_path: Optional[str] = None,
) -> None:
    """Run the single Config menu with explicit Feature and menu injection."""
    if initial_path:
        _dispatch_initial_path(
            initial_path,
            providers,
            principal,
            provider_login,
            runtime_menus,
            menu,
        )
    while True:
        clear_screen()
        print_banner()
        print_tui_panel(
            "Config Center / Runtime Config",
            "AI runtime core config; other settings in Web console",
        )
        choice = menu.choose(
            "Config Center",
            (
                MenuItem("1", "Provider and Model Configuration"),
                MenuItem("2", "Agent Capability Validation"),
                MenuItem("3", "Food Strategy Configuration"),
                MenuItem("4", "View Current Config"),
                MenuItem("5", "Reset Runtime Config"),
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
            runtime_menus.tool_menu()
        elif choice == "3":
            runtime_menus.food_menu()
        elif choice == "4":
            show_config(providers, settings, principal)
        elif choice == "5":
            reset_config(settings, principal)


def _dispatch_initial_path(
    initial_path: str,
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_login: ProviderLogin,
    runtime_menus: RuntimeConfigMenus,
    menu: TerminalMenuPort,
) -> None:
    path = initial_path.strip().lower()
    if path in {"provider", "providers"}:
        config_providers(providers, principal, provider_login, menu)
    elif path in {"agent", "tools"}:
        runtime_menus.tool_menu()
    elif path in {"food", "foods"}:
        runtime_menus.food_menu()
    elif path == "login":
        provider_login("ollama")


__all__ = ("ProviderLogin", "RuntimeConfigMenus", "run_config_tui")
