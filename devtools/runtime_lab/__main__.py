"""Runtime 开发配置 TUI 菜单（复用 ai_runtime/lab/cli.py:RuntimeLab）。"""

from ai_runtime.lab.cli import RuntimeLab
from ai_runtime.storage.data_home import get_elfie_developer_home


def main() -> int:
    """启动开发环境 Runtime 配置 TUI。"""
    config_home = get_elfie_developer_home() / "runtime_lab"
    lab = RuntimeLab(config_home=config_home)
    lab.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
