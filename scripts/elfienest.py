from __future__ import annotations

import argparse
import os
import sys
from typing import NoReturn

PINNED_CPYTHON_VERSION = (3, 9, 25)

if (
    sys.implementation.name != "cpython"
    or sys.version_info[:3] != PINNED_CPYTHON_VERSION
):
    actual_version = ".".join(str(part) for part in sys.version_info[:3])
    sys.stderr.write(
        "❌ ElfieNest 必须使用 CPython 3.9.25；"
        f"当前是 {sys.implementation.name} {actual_version}。\n"
    )
    raise SystemExit(1)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfienest.cli.admin_commands import dispatch_admin
from elfienest.cli.model_commands import dispatch_models
from elfienest.cli.provider_commands import dispatch_providers, login_provider
from elfienest.cli.route_commands import dispatch_route
from elfienest.cli.runtime_commands import (
    dispatch_db,
    restart_service,
    show_logs,
    show_sessions,
    show_stats,
    show_status,
    show_version,
    start_web,
    stop_service,
)
from elfienest.cli.tui.common import print_banner
from elfienest.cli.tui.config_app import run_config_tui
from elfienest.cli.tui.setup_app import run_setup_wizard


class SecretSafeArgumentParser(argparse.ArgumentParser):
    """避免 argparse 在错误信息中回显可能误输的秘密。"""

    def error(self, message: str) -> NoReturn:
        if sys.argv[1:3] == ["admin", "reset-password"]:
            self.print_usage(sys.stderr)
            self.exit(2, f"{self.prog}: 参数无效\n")
        super().error(message)


def main() -> None:
    parser = SecretSafeArgumentParser(
        prog="elfienest",
        description="ElfieNest CLI - 仿生生命体系统命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    subparsers.add_parser("config", help="交互式配置 TUI")

    models_parser = subparsers.add_parser("models", help="模型管理")
    models_parser.add_argument(
        "models_command",
        nargs="?",
        choices=["list", "scan"],
        default="list",
        help="模型命令",
    )

    providers_parser = subparsers.add_parser("providers", help="管理服务商")
    providers_parser.add_argument(
        "providers_command",
        nargs="?",
        choices=["list", "test", "add", "remove"],
        default="list",
        help="服务商命令",
    )
    providers_parser.add_argument("provider_id", nargs="?", help="服务商标识")

    login_parser = subparsers.add_parser("login", help="配置服务商 API Key")
    login_parser.add_argument("provider", help="服务商标识 (如 openai, deepseek)")

    route_parser = subparsers.add_parser("route", help="模型路由管理")
    route_parser.add_argument("route_command", choices=["show"], help="路由命令")
    route_parser.add_argument("elfie_id", nargs="?", help="精灵 ID")

    subparsers.add_parser("status", help="查看服务状态")
    subparsers.add_parser("web", help="启动服务并打开浏览器")
    subparsers.add_parser("stats", help="显示使用统计")
    subparsers.add_parser("session", help="管理会话")
    subparsers.add_parser("logs", help="查看日志")
    subparsers.add_parser("version", help="显示版本")
    subparsers.add_parser("setup", help="首次设置向导")
    subparsers.add_parser("restart", help="重启服务")
    subparsers.add_parser("stop", help="停止服务")

    db_parser = subparsers.add_parser("db", help="数据库工具")
    db_parser.add_argument(
        "db_command", nargs="?", choices=["backup", "reset"], help="数据库命令"
    )

    admin_parser = subparsers.add_parser("admin", help="管理员账号管理")
    admin_subparsers = admin_parser.add_subparsers(
        dest="admin_command",
        help="管理员命令",
        parser_class=SecretSafeArgumentParser,
    )
    admin_subparsers.add_parser("show", help="显示当前管理员")
    reset_admin_parser = admin_subparsers.add_parser(
        "reset-password", help="安全重置现有管理员密码"
    )
    reset_admin_parser.add_argument(
        "admin_username",
        nargs="?",
        metavar="username",
        help="管理员用户名；只有一个管理员时可省略",
    )
    admin_parser.set_defaults(admin_username=None)

    args = parser.parse_args()
    dispatch_command(args)


def dispatch_command(args: argparse.Namespace) -> None:
    if args.command == "config":
        run_config_tui(login_provider)
    elif args.command == "models":
        dispatch_models(args.models_command)
    elif args.command == "providers":
        dispatch_providers(args.providers_command, args.provider_id)
    elif args.command == "login":
        login_provider(args.provider)
    elif args.command == "route":
        dispatch_route(args.route_command, args.elfie_id)
    elif args.command == "status":
        show_status()
    elif args.command == "web":
        start_web()
    elif args.command == "stats":
        show_stats()
    elif args.command == "session":
        show_sessions()
    elif args.command == "logs":
        show_logs()
    elif args.command == "db":
        dispatch_db(args.db_command)
    elif args.command == "admin":
        raise SystemExit(dispatch_admin(args.admin_command, args.admin_username))
    elif args.command == "version":
        show_version()
    elif args.command == "setup":
        run_setup_wizard()
    elif args.command == "restart":
        restart_service()
    elif args.command == "stop":
        stop_service()
    else:
        print_banner()
        print("  启动服务...")
        print()
        os.execvp(sys.executable, [sys.executable, "scripts/serve.py"] + sys.argv[1:])


if __name__ == "__main__":
    main()
