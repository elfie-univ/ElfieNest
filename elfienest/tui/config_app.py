from __future__ import annotations

from typing import Callable

from elfienest.config.user_config import read_user_config
from elfienest.tui.common import clear_screen, print_banner, print_tui_panel
from elfienest.tui.config_editors import (
    config_adoption,
    config_engine,
    config_llm,
    config_security,
)
from elfienest.tui.config_views import reset_config, show_config, test_config
from elfienest.tui.provider_menu import config_providers

ProviderLogin = Callable[[str], None]


def run_config_tui(provider_login: ProviderLogin) -> None:
    while True:
        clear_screen()
        print_banner()
        config = read_user_config()

        print_tui_panel("配置菜单", "管理模型、服务商、引擎、安全与精灵领养配置")
        print("  1. 查看当前配置")
        print("  2. 配置大模型 (LLM)")
        print("  3. 配置服务商 (Providers)")
        print("  4. 配置引擎参数")
        print("  5. 配置安全设置")
        print("  6. 配置精灵领养")
        print("  7. 测试配置")
        print("  8. 重置为默认配置")
        print("  0. 退出")
        print()

        try:
            choice = input("请选择 [0-8]: ").strip()
        except KeyboardInterrupt:
            print("\n再见！")
            break

        if choice == "0":
            print("\n再见！")
            break
        if choice == "1":
            show_config(config)
        elif choice == "2":
            config_llm(config)
        elif choice == "3":
            config_providers(config, provider_login)
        elif choice == "4":
            config_engine(config)
        elif choice == "5":
            config_security(config)
        elif choice == "6":
            config_adoption(config)
        elif choice == "7":
            test_config(config)
        elif choice == "8":
            reset_config()
