from __future__ import annotations

from typing import Callable

from elfienest.cli.tui.common import clear_screen, print_banner, print_tui_panel
from elfienest.cli.tui.config_editors import (
    config_adoption,
    config_engine,
    config_security,
)
from elfienest.cli.tui.config_views import reset_config, show_config, test_config
from elfienest.config.user_config import read_user_config
from runtime.lab.cli import RuntimeLab

ProviderLogin = Callable[[str], None]


def run_config_tui(provider_login: ProviderLogin) -> None:
    runtime_lab = RuntimeLab()
    while True:
        clear_screen()
        print_banner()
        config = read_user_config()

        print_tui_panel("配置菜单", "三层 Runtime 配置与 ElfieNest 应用配置")
        print("  1. 第一层：Provider 与原始模型")
        print("  2. 第二层：Agent 基础工具")
        print("  3. 第三层：粮食策略")
        print("  4. 查看当前配置")
        print("  5. 配置引擎参数")
        print("  6. 配置安全设置")
        print("  7. 配置精灵领养")
        print("  8. 测试应用配置")
        print("  9. 重置应用配置")
        print("  0. 退出")
        print()

        try:
            choice = input("请选择 [0-9]: ").strip()
        except KeyboardInterrupt:
            print("\n再见！")
            break

        if choice == "0":
            print("\n再见！")
            break
        if choice == "1":
            runtime_lab.provider_menu()
        elif choice == "2":
            runtime_lab.agent_menu()
        elif choice == "3":
            runtime_lab.food_menu()
        elif choice == "4":
            show_config(config)
        elif choice == "5":
            config_engine(config)
        elif choice == "6":
            config_security(config)
        elif choice == "7":
            config_adoption(config)
        elif choice == "8":
            test_config(config)
        elif choice == "9":
            reset_config()
