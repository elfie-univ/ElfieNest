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

from app.interfaces.cli.doctor_commands import run_doctor
from app.interfaces.cli.lifecycle_commands import (
    default_service_command,
    open_web_console,
    restart_background_service,
    show_service_status,
    start_background_service,
    start_desktop_application,
    stop_background_service,
)
from app.interfaces.cli.owner_commands import run_owner_menu
from app.interfaces.cli.provider_commands import login_provider
from app.interfaces.cli.runtime_commands import (
    dispatch_db,
    show_version,
)
from app.interfaces.cli.tui.common import print_banner
from app.interfaces.cli.tui.config_app import run_config_tui
from app.interfaces.cli.tui.setup_app import run_setup_wizard
from app.orchestration.lifecycle.types import ServiceLifecycleResult


class SecretSafeArgumentParser(argparse.ArgumentParser):
    """避免 argparse 在错误信息中回显可能误输的秘密。"""

    def error(self, message: str) -> NoReturn:
        sensitive_options = {
            "--api-key",
            "--password",
            "--secret",
            "--token",
        }
        has_sensitive_argument = any(
            argument.split("=", 1)[0] in sensitive_options for argument in sys.argv[1:]
        )
        if has_sensitive_argument:
            self.print_usage(sys.stderr)
            self.exit(2, f"{self.prog}: 参数无效\n")
        if "owner" in sys.argv[1:]:
            self.print_usage(sys.stderr)
            self.exit(2, f"{self.prog}: Owner 参数无效\n")
        super().error(message)


def main() -> None:
    parser = SecretSafeArgumentParser(
        prog="elfienest",
        description="ElfieNest CLI - 仿生生命体系统命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="命令",
        parser_class=SecretSafeArgumentParser,
    )

    config_parser = subparsers.add_parser("config", help="配置中心（方向键菜单）")
    config_parser.add_argument(
        "config_path",
        nargs="?",
        choices=["provider", "providers", "agent", "tools", "food", "owner", "doctor"],
        help=argparse.SUPPRESS,
    )

    serve_parser = subparsers.add_parser(
        "serve", help="开发/诊断模式前台运行服务并实时显示日志"
    )
    serve_parser.add_argument("--fallback", action="store_true")
    serve_parser.add_argument("--force", action="store_true")
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--ws-port", type=int, default=None)
    serve_parser.add_argument("--godot-ws-port", type=int, default=None)
    serve_parser.add_argument("--no-seed-elfie", action="store_true")

    start_parser = subparsers.add_parser(
        "start", help="后台启动服务（已运行时不重复启动）"
    )
    start_parser.add_argument("--port", type=int, default=None)
    start_parser.add_argument("--ws-port", type=int, default=None)
    start_parser.add_argument("--godot-ws-port", type=int, default=None)
    start_parser.add_argument("--fallback", action="store_true")
    start_parser.add_argument("--no-seed-elfie", action="store_true")
    start_network_group = start_parser.add_mutually_exclusive_group()
    start_network_group.add_argument(
        "--lan",
        dest="lan",
        action="store_true",
        default=True,
        help="允许局域网访问（产品后台启动默认开启）",
    )
    start_network_group.add_argument(
        "--loopback",
        dest="lan",
        action="store_false",
        help="仅绑定本机回环地址",
    )
    subparsers.add_parser("status", help="查看服务状态")
    subparsers.add_parser("web", help="确保服务可用并打开 Web 管理台")
    subparsers.add_parser("desktop", help="显式启动打包版 ElfieNest Desktop")
    subparsers.add_parser("stop", help="停止服务")
    subparsers.add_parser("restart", help="强制重启服务")
    subparsers.add_parser("owner", help="Owner 账户菜单")
    subparsers.add_parser("doctor", help="运行本地诊断与配置检查")
    subparsers.add_parser("version", help="显示版本")
    subparsers.add_parser("setup", help="首次设置向导")
    db_parser = subparsers.add_parser("db", help="数据库工具")
    db_parser.add_argument(
        "db_command", nargs="?", choices=["backup", "reset"], help="数据库命令"
    )

    args = parser.parse_args()
    dispatch_command(args)


def dispatch_command(args: argparse.Namespace) -> None:
    try:
        _dispatch_command(args)
    except KeyboardInterrupt as error:
        print()
        print("  已取消。")
        raise SystemExit(130) from error


def _dispatch_command(args: argparse.Namespace) -> None:
    if args.command == "config":
        run_config_tui(login_provider, getattr(args, "config_path", None))
    elif args.command == "serve":
        options = _service_options_from_args(args)
        if args.force:
            options += ("--force",)
        os.execvp(
            sys.executable,
            [sys.executable, "scripts/serve.py", *options],
        )
    elif args.command == "status":
        show_service_status()
    elif args.command == "web":
        _exit_on_lifecycle_failure(open_web_console())
    elif args.command == "desktop":
        _exit_on_lifecycle_failure(start_desktop_application())
    elif args.command == "start":
        _exit_on_lifecycle_failure(
            start_background_service(
                default_service_command(_service_options_from_args(args))
            )
        )
    elif args.command == "stop":
        _exit_on_lifecycle_failure(stop_background_service())
    elif args.command == "restart":
        _exit_on_lifecycle_failure(restart_background_service())
    elif args.command == "owner":
        raise SystemExit(run_owner_menu())
    elif args.command == "doctor":
        raise SystemExit(run_doctor())
    elif args.command == "db":
        dispatch_db(args.db_command)
    elif args.command == "version":
        show_version()
    elif args.command == "setup":
        run_setup_wizard()
    else:
        print_banner()
        print("  启动服务...")
        print()
        os.execvp(sys.executable, [sys.executable, "scripts/serve.py"] + sys.argv[1:])


def _service_options_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    """Convert supported background start options to the service command."""
    options: list[str] = []
    if args.port is not None:
        options.extend(("--port", str(args.port)))
    if args.ws_port is not None:
        options.extend(("--ws-port", str(args.ws_port)))
    if args.godot_ws_port is not None:
        options.extend(("--godot-ws-port", str(args.godot_ws_port)))
    if args.fallback:
        options.append("--fallback")
    if args.no_seed_elfie:
        options.append("--no-seed-elfie")
    if getattr(args, "lan", False):
        options.append("--lan")
    return tuple(options)


def _exit_on_lifecycle_failure(result: ServiceLifecycleResult) -> None:
    """将生命周期失败转换为可脚本判断的非零退出码。"""
    if getattr(result, "status", None) == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
