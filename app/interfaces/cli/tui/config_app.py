from __future__ import annotations

from typing import Callable, Optional

from ai_runtime.lab.cli import RuntimeLab
from ai_runtime.lab.menu import MenuItem, TerminalMenu
from app.features.configuration.user_config import read_user_config
from app.interfaces.cli.tui.common import clear_screen, print_banner, print_tui_panel
from app.interfaces.cli.tui.config_views import reset_config, show_config

ProviderLogin = Callable[[str], None]


def run_config_tui(
    provider_login: ProviderLogin,
    initial_path: Optional[str] = None,
) -> None:
    """Run the single Config menu with arrow-key navigation in a TTY."""
    runtime_lab = RuntimeLab()
    menu = TerminalMenu(input_fn=input, output_fn=print)
    if initial_path:
        _dispatch_initial_path(initial_path, runtime_lab, provider_login)
    while True:
        clear_screen()
        print_banner()
        config = read_user_config()
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
            runtime_lab.provider_menu()
        elif choice == "2":
            runtime_lab.tool_menu()
        elif choice == "3":
            runtime_lab.food_menu()
        elif choice == "4":
            show_config(config)
        elif choice == "5":
            reset_config()


def _dispatch_initial_path(
    initial_path: str,
    runtime_lab: RuntimeLab,
    provider_login: ProviderLogin,
) -> None:
    """Open an explicitly requested second-level path once before the menu."""
    path = initial_path.strip().lower()
    if path in {"provider", "providers"}:
        runtime_lab.provider_menu()
    elif path in {"agent", "tools"}:
        runtime_lab.tool_menu()
    elif path in {"food", "foods"}:
        runtime_lab.food_menu()
    elif path == "login":
        provider_login("ollama")
