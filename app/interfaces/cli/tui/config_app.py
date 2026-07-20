from __future__ import annotations

from typing import Callable, Optional

from app.interfaces.cli.doctor_commands import run_doctor
from app.interfaces.cli.owner_commands import run_owner_menu
from app.interfaces.cli.tui.common import clear_screen, print_banner, print_tui_panel
from app.interfaces.cli.tui.config_editors import (
    config_adoption,
    config_engine,
)
from app.interfaces.cli.tui.config_views import reset_config, show_config
from app.features.configuration.user_config import read_user_config
from ai_runtime.lab.cli import RuntimeLab
from ai_runtime.lab.menu import MenuItem, TerminalMenu

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
            "配置中心 / 核心配置",
            "KUI 只放基础核心项；精灵细节与高级安全策略在 Web 管理页处理",
        )
        choice = menu.choose(
            "配置中心",
            (
                MenuItem("1", "Runtime / Provider 与模型"),
                MenuItem("2", "Runtime / Agent 基础能力"),
                MenuItem("3", "Runtime / 粮食策略"),
                MenuItem("4", "应用 / 引擎参数"),
                MenuItem("5", "应用 / 精灵领养"),
                MenuItem("6", "Owner 账户"),
                MenuItem("7", "诊断并自动修复（Doctor）"),
                MenuItem("8", "查看当前配置"),
                MenuItem("9", "重置应用配置"),
            ),
            breadcrumb="ElfieNest / Config",
            back_label="返回首页",
        )
        if choice is None:
            print("\n再见！")
            return
        if choice == "1":
            runtime_lab.provider_menu()
        elif choice == "2":
            runtime_lab.agent_menu()
        elif choice == "3":
            runtime_lab.food_menu()
        elif choice == "4":
            config_engine(config)
        elif choice == "5":
            config_adoption(config)
        elif choice == "6":
            run_owner_menu()
        elif choice == "7":
            run_doctor()
        elif choice == "8":
            show_config(config)
        elif choice == "9":
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
        runtime_lab.agent_menu()
    elif path in {"food", "foods"}:
        runtime_lab.food_menu()
    elif path == "owner":
        run_owner_menu()
    elif path in {"doctor", "verify"}:
        run_doctor()
    elif path == "login":
        provider_login("ollama")
