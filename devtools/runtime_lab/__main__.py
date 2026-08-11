"""Runtime 开发配置 TUI 菜单。"""

from infrastructure.persistence.data_home import get_elfie_developer_home
from infrastructure.platform.runtime_lab import RuntimeLab


def main() -> int:
    """启动开发环境 Runtime 配置 TUI。"""
    config_home = get_elfie_developer_home() / "runtime_lab"
    lab = RuntimeLab(config_home=config_home)
    lab.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
