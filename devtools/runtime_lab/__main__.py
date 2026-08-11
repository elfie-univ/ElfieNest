"""Runtime 开发配置 TUI 菜单。"""

import argparse

from devtools.runtime_lab.lab import RuntimeLab
from infrastructure.persistence.layout.data_home import get_elfie_developer_home


def main() -> int:
    """启动开发环境 Runtime 配置 TUI。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=("all", "tools", "food"), default="all")
    args = parser.parse_args()
    config_home = get_elfie_developer_home() / "runtime_lab"
    lab = RuntimeLab(config_home=config_home)
    if args.section == "tools":
        lab.tool_menu()
    elif args.section == "food":
        lab.food_menu()
    else:
        lab.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
