from __future__ import annotations

import argparse
import os
import shlex
import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Iterator, NoReturn, Optional, Sequence

PINNED_CPYTHON_VERSION = (3, 9, 25)

if (
    sys.implementation.name != "cpython"
    or sys.version_info[:3] != PINNED_CPYTHON_VERSION
):
    actual_version = ".".join(str(part) for part in sys.version_info[:3])
    sys.stderr.write(
        "❌ ElfieNest requires CPython 3.9.25; "
        f"current is {sys.implementation.name} {actual_version}.\n"
    )
    raise SystemExit(1)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.bootstrap.app_wiring.accounts import build_accounts_service
from app.bootstrap.app_wiring.cli_configuration import build_cli_configuration
from app.bootstrap.app_wiring.cli_ui import build_terminal_menu
from app.bootstrap.app_wiring.operations import build_operations_facade
from app.bootstrap.system_wiring.entrypoints import (
    DataHomeSelectionError,
    get_db_path,
    get_db_path_for_home,
    resolve_elfie_home,
)
from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli.data_home_commands import (
    inspect_data_home_command,
    recover_data_home_command,
)
from app.interfaces.cli.doctor_commands import run_doctor
from app.interfaces.cli.foreground_runtime import run_foreground_service
from app.interfaces.cli.lifecycle_commands import (
    display_data_home,
    open_desktop_application,
    open_web_console,
    published_http_port_for_home,
    restart_background_service,
    selected_runtime_data_home,
    show_service_status,
    start_background_service,
    stop_background_service,
)
from app.interfaces.cli.mobile_commands import show_mobile_access
from app.interfaces.cli.owner_commands import run_owner_menu
from app.interfaces.cli.packaged_runtime import (
    PackagedCliRuntimeError,
    configure_frozen_cli_runtime,
)
from app.interfaces.cli.provider_commands import login_provider
from app.interfaces.cli.runtime_commands import dispatch_db, show_version
from app.interfaces.cli.target_context import (
    CliSession,
    prompt_for_candidate,
    resolve_cli_target,
    source_root_for_cli,
)
from app.interfaces.cli.tui.common import print_banner
from app.interfaces.cli.tui.config_app import run_config_tui
from app.interfaces.cli.uninstall_commands import run_uninstall_menu
from app.orchestration.lifecycle import (
    EntrypointMode,
    LifecycleFacade,
    ServiceLifecycleResult,
    TargetResolutionError,
)

if getattr(sys, "frozen", False):
    try:
        configure_frozen_cli_runtime(Path(sys.executable), sys.platform, os.environ)
    except PackagedCliRuntimeError as error:
        sys.stderr.write(f"❌ {error}\n")
        raise SystemExit(1) from error


class SecretSafeArgumentParser(argparse.ArgumentParser):
    """Prevent argparse errors from echoing secrets that may have been mistyped."""

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
            self.exit(2, f"{self.prog}: invalid argument\n")
        if "owner" in sys.argv[1:]:
            self.print_usage(sys.stderr)
            self.exit(2, f"{self.prog}: invalid Owner argument\n")
        super().error(message)


def build_parser() -> SecretSafeArgumentParser:
    """Build the mode-specific parser shared by one-shot and interactive CLI."""
    parser = SecretSafeArgumentParser(
        prog="elfienest",
        description="ElfieNest CLI - Embodied AI Creature System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    packaged = _is_packaged_cli_runtime()

    subparsers = parser.add_subparsers(
        dest="command",
        help="commands",
        parser_class=SecretSafeArgumentParser,
    )

    if not packaged:
        serve_parser = subparsers.add_parser(
            "serve", help="Run service in foreground (dev mode)"
        )
        serve_parser.add_argument("--port", type=int, default=None)
        serve_parser.add_argument("--godot-ws-port", type=int, default=None)
        serve_parser.add_argument(
            "--data-home",
            default=None,
            help="Use an isolated source/development data root",
        )
        serve_parser.add_argument("--lan", action="store_true")
        serve_parser.add_argument(
            "--runtime-mode",
            choices=("development", "release"),
            default=None,
        )

    start_parser = subparsers.add_parser("start", help="Start background service")
    if not packaged:
        start_parser.add_argument("--port", type=int, default=None)
        start_parser.add_argument("--godot-ws-port", type=int, default=None)
        start_parser.add_argument(
            "--data-home",
            default=None,
            help="Use an isolated source/development data root",
        )
    start_parser.add_argument("--owner-id", default="cli", help=argparse.SUPPRESS)
    start_parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    start_parser.add_argument(
        "--progress-json", action="store_true", help=argparse.SUPPRESS
    )
    start_network_group = start_parser.add_mutually_exclusive_group()
    start_network_group.add_argument(
        "--lan",
        dest="lan",
        action="store_true",
        default=True,
        help=(
            "Allow LAN access (default for background start)"
            if not packaged
            else argparse.SUPPRESS
        ),
    )
    start_network_group.add_argument(
        "--loopback",
        dest="lan",
        action="store_false",
        help=("Bind to loopback only" if not packaged else argparse.SUPPRESS),
    )

    restart_parser = subparsers.add_parser("restart", help="Force restart service")
    if not packaged:
        restart_parser.add_argument("--port", type=int, default=None)
        restart_parser.add_argument("--godot-ws-port", type=int, default=None)
        restart_parser.add_argument(
            "--data-home",
            default=None,
            help="Use an isolated source/development data root",
        )

    stop_parser = subparsers.add_parser("stop", help="Stop service")
    stop_parser.add_argument("--owner-id", default="cli", help=argparse.SUPPRESS)
    if not packaged:
        stop_parser.add_argument(
            "--data-home",
            default=None,
            help="Use an isolated source/development data root",
        )

    status_parser = subparsers.add_parser("status", help="Show service status")
    status_parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    subparsers.add_parser(
        "web",
        help="Open Web console for an already running service",
    )
    subparsers.add_parser("mobile", help="Show mobile access URL and QR code")
    if packaged:
        subparsers.add_parser(
            "desktop",
            help="Open the existing Desktop Viewer without starting service",
        )

    config_parser = subparsers.add_parser(
        "config", help="Config center (interactive menu)"
    )
    config_parser.add_argument(
        "config_path",
        nargs="?",
        choices=["provider", "providers", "agent", "tools", "food", "foods"],
        help=argparse.SUPPRESS,
    )
    subparsers.add_parser("owner", help="Owner account menu")
    subparsers.add_parser("doctor", help="Run local diagnostics and config check")
    db_parser = subparsers.add_parser("db", help="Database tools")
    db_parser.add_argument(
        "db_command", nargs="?", choices=["backup", "reset"], help="Database command"
    )
    if packaged:
        subparsers.add_parser("uninstall", help="Uninstall and data cleanup")
    subparsers.add_parser("version", help="Show version")

    parser.add_argument("--interactive", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--__controller-action",
        choices=("inspect-data-home", "recover-data-home"),
        dest="internal_controller_action",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--__controller-data-home",
        dest="internal_controller_data_home",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _is_packaged_cli_runtime() and (
        not arguments or any(argument in {"-h", "--help"} for argument in arguments)
    ):
        print_banner()
    args = parser.parse_args(arguments)
    if getattr(args, "internal_controller_action", None) is not None:
        _dispatch_internal_controller_command(args)
        return
    if getattr(args, "interactive", False):
        run_interactive_shell()
        return
    if args.command is None:
        parser.print_help()
        return
    dispatch_command(args)


def run_interactive_shell() -> None:
    """Run a persistent source shell with in-memory target context."""
    session = CliSession()
    source_root = source_root_for_cli()
    state = create_lifecycle_facade().source_cli_state(source_root)
    history: Sequence[str] = ()
    try:
        history = state.load_history()
    except OSError as error:
        print(f"⚠️ 源码 CLI history 不可用: {error}")
    _configure_readline_history(history)
    print_banner()
    print_cli_help()
    while True:
        try:
            input_line = input("elfienest> ")
        except EOFError:
            print()
            return
        if not input_line.strip():
            continue
        try:
            argv = shlex.split(input_line)
        except ValueError as error:
            print(f"❌ 命令解析失败: {error}")
            continue
        command = argv[0]
        if command in {"exit", "quit", "q"}:
            print("\n  Goodbye! 🦊\n")
            return
        if command in {"help", "h", "?"}:
            print_cli_help()
            continue
        if command == "v":
            argv = ["version", *argv[1:]]
        if _safe_interactive_history(input_line):
            try:
                state.record_history(input_line)
            except OSError as error:
                print(f"⚠️ 源码 CLI history 不可写，已继续执行: {error}")
        try:
            args = build_parser().parse_args(argv)
            dispatch_command(args, session=session, interactive=True)
        except SystemExit as error:
            if error.code not in (0, None):
                print(f"❌ 命令失败，退出码: {error.code}")
        except (TargetResolutionError, DataHomeSelectionError) as error:
            print(f"❌ {error}")


def _configure_readline_history(history: Sequence[str]) -> None:
    """Enable terminal history when the host provides the optional readline module."""
    try:
        import readline
    except ImportError:
        return
    for line in history:
        readline.add_history(line)
    readline.set_history_length(50)


def print_cli_help() -> None:
    """Print the compact command list used by the interactive shell."""
    packaged = _is_packaged_cli_runtime()
    commands = []
    if not packaged:
        commands.append(("serve*", "Run service in foreground (dev mode)"))
    commands.extend(
        [
            ("start*" if not packaged else "start", "Start background service"),
            ("restart*" if not packaged else "restart", "Force restart service"),
            ("stop*" if not packaged else "stop", "Stop current service"),
            ("status*", "Show service and port status"),
            ("web", "Open Web console for an already running service"),
            ("mobile", "Show mobile access URL and QR code"),
        ]
    )
    if packaged:
        commands.append(("desktop", "Open the existing Desktop Viewer"))
    commands.extend(
        [
            (
                "config",
                "Provider, model, Food and tool configuration (interactive menu)",
            ),
            ("owner", "Owner account menu"),
            ("doctor", "Run local diagnostics and auto-repair"),
            ("db*", "Database tools"),
        ]
    )
    if packaged:
        commands.append(("uninstall", "Uninstall and data cleanup"))
    commands.append(("version", "Show version info"))
    if not packaged:
        commands.extend(
            [
                ("help", "Show this help"),
                ("exit", "Exit interactive mode"),
            ]
        )

    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │  Commands                                               │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()
    for command, description in commands:
        print(f"    {command:<15} {description}")
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │  Examples                                               │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()
    if not packaged:
        print("    elfienest> serve              # Start with the configured model")
        print("    elfienest> exit               # Exit")
    print()


def _safe_interactive_history(command_line: str) -> bool:
    try:
        arguments = shlex.split(command_line)
    except ValueError:
        return False
    if not arguments or arguments[0] in {"owner", "config"}:
        return False
    sensitive = {"--api-key", "--password", "--secret", "--token"}
    return not any(argument.split("=", 1)[0] in sensitive for argument in arguments)


def dispatch_command(
    args: argparse.Namespace,
    lifecycle: LifecycleFacade | None = None,
    *,
    session: CliSession | None = None,
    interactive: bool = False,
) -> None:
    if getattr(args, "command", None) == "version":
        show_version()
        return
    lifecycle_client = lifecycle or create_lifecycle_facade()
    try:
        target = None
        if _command_requires_target(args):
            target = resolve_cli_target(
                lifecycle_client,
                command=args.command,
                mode=(
                    EntrypointMode.INSTALLED
                    if _is_packaged_cli_runtime()
                    else EntrypointMode.SOURCE
                ),
                source_root=source_root_for_cli(),
                invoking_cwd=Path.cwd(),
                explicit_home=getattr(args, "data_home", None),
                session=session,
                installed_environment=dict(os.environ),
                prompt=(
                    prompt_for_candidate if interactive or sys.stdin.isatty() else None
                ),
            )
        if (
            target is not None
            and _is_packaged_cli_runtime()
            and args.command in {"status", "web", "mobile", "desktop"}
        ):
            _verify_installed_controller_target(
                lifecycle_client,
                target.home,
                command=args.command,
                require_controller=args.command != "status",
            )
        with _target_environment(
            target.home if target is not None else None,
            target.display_home if target is not None else None,
        ):
            _dispatch_command(
                args,
                lifecycle_client,
                selected_home=target.home if target is not None else None,
                display_home=target.display_home if target is not None else None,
            )
    except DataHomeSelectionError as error:
        sys.stderr.write(f"elfienest: {error}\n")
        raise SystemExit(2) from error
    except TargetResolutionError as error:
        sys.stderr.write(f"elfienest: {error}\n")
        raise SystemExit(2) from error
    except KeyboardInterrupt as error:
        print()
        print("  Cancelled.")
        raise SystemExit(130) from error


def _command_requires_target(args: argparse.Namespace) -> bool:
    return getattr(args, "command", None) not in {None, "version"}


def _dispatch_internal_controller_command(args: argparse.Namespace) -> None:
    """Handle Desktop-only data-root maintenance without a public CLI command."""
    if os.environ.get("ELFIENEST_CONTROLLER_CLIENT") != "1":
        raise DataHomeSelectionError(
            "内部 Controller 数据目录接口只能由 Desktop Controller 调用"
        )
    action = args.internal_controller_action
    explicit_home = args.internal_controller_data_home
    if action == "inspect-data-home":
        raise SystemExit(
            inspect_data_home_command(
                create_lifecycle_facade(),
                explicit_home=explicit_home,
                json_output=True,
            )
        )
    if action == "recover-data-home":
        raise SystemExit(
            recover_data_home_command(
                create_lifecycle_facade(),
                explicit_home=explicit_home,
                json_output=True,
            )
        )
    raise DataHomeSelectionError(f"未知内部 Controller 操作: {action}")


@contextmanager
def _target_environment(
    home: Path | None, display_home: str | None = None
) -> Iterator[None]:
    """Expose only the display label; data roots are passed explicitly."""
    del home
    with display_data_home(display_home):
        yield


def _dispatch_command(
    args: argparse.Namespace,
    lifecycle: LifecycleFacade,
    *,
    selected_home: Path | None = None,
    display_home: str | None = None,
) -> None:
    if args.command == "config":
        configuration = build_cli_configuration(_db_path_for_command(selected_home))
        run_config_tui(
            configuration.providers,
            configuration.food,
            configuration.capabilities,
            configuration.settings,
            configuration.principal,
            partial(
                login_provider,
                configuration.providers,
                configuration.principal,
            ),
            build_terminal_menu(),
            getattr(args, "config_path", None),
        )
    elif args.command == "serve":
        options = _service_options_from_args(args, selected_home=selected_home)
        if selected_home is None:
            result = run_foreground_service(lifecycle, options)
        else:
            result = run_foreground_service(
                lifecycle,
                options,
                selected_home=selected_home,
            )
        _exit_on_lifecycle_failure(result)
    elif args.command == "status":
        if selected_home is None:
            show_service_status(lifecycle, json_output=getattr(args, "json", False))
        else:
            show_service_status(
                lifecycle,
                json_output=getattr(args, "json", False),
                selected_home=selected_home,
            )
    elif args.command == "web":
        result = (
            open_web_console(lifecycle)
            if selected_home is None
            else open_web_console(lifecycle, selected_home=selected_home)
        )
        _exit_on_lifecycle_failure(result)
    elif args.command == "desktop":
        result = (
            open_desktop_application(lifecycle)
            if selected_home is None
            else open_desktop_application(lifecycle, selected_home=selected_home)
        )
        _exit_on_lifecycle_failure(result)
    elif args.command == "mobile":
        if selected_home is None:
            selected_home = selected_runtime_data_home(lifecycle)
        else:
            selected_home = selected_runtime_data_home(
                lifecycle,
                selected_home=selected_home,
            )
        raise SystemExit(
            show_mobile_access(
                lifecycle,
                build_operations_facade(_db_path_for_command(selected_home)),
                http_port=published_http_port_for_home(lifecycle, selected_home),
                data_home=selected_home,
                display_home=display_home,
                clear_terminal=False,
            )
        )
    elif args.command == "start":
        command = lifecycle.default_service_command(
            _service_options_from_args(args, selected_home=selected_home)
        )
        owner_id = getattr(args, "owner_id", None)
        if selected_home is None:
            result = start_background_service(
                lifecycle,
                command,
                owner_id=owner_id or "cli",
                json_output=getattr(args, "json", False),
                progress_json=getattr(args, "progress_json", False),
            )
        else:
            result = start_background_service(
                lifecycle,
                command,
                owner_id=owner_id or "cli",
                json_output=getattr(args, "json", False),
                progress_json=getattr(args, "progress_json", False),
                selected_home=selected_home,
            )
        _exit_on_lifecycle_failure(result)
    elif args.command == "stop":
        owner_id = getattr(args, "owner_id", None)
        if selected_home is None:
            result = stop_background_service(lifecycle, owner_id=owner_id or "cli")
        else:
            result = stop_background_service(
                lifecycle,
                owner_id=owner_id or "cli",
                selected_home=selected_home,
            )
        _exit_on_lifecycle_failure(result)
    elif args.command == "restart":
        restart_options = _service_options_from_args(args, selected_home=selected_home)
        if selected_home is None:
            result = restart_background_service(lifecycle, restart_options)
        else:
            result = restart_background_service(
                lifecycle,
                restart_options,
                selected_home=selected_home,
            )
        _exit_on_lifecycle_failure(result)
    elif args.command == "owner":
        owner_db_path = _db_path_for_command(selected_home)
        raise SystemExit(
            run_owner_menu(
                lifecycle,
                build_accounts_service(owner_db_path),
                build_terminal_menu(),
                owner_db_path,
            )
        )
    elif args.command == "doctor":
        raise SystemExit(run_doctor(lifecycle, selected_home=selected_home))
    elif args.command == "uninstall":
        raise SystemExit(
            run_uninstall_menu(
                lifecycle,
                build_terminal_menu(),
                selected_home=selected_home,
            )
        )
    elif args.command == "version":
        show_version()
    elif args.command == "db":
        dispatch_db(
            build_operations_facade(_db_path_for_command(selected_home)),
            getattr(args, "db_command", None),
        )
    else:
        print_banner()
        print("  Starting service...")
        print()
        if selected_home is None:
            result = run_foreground_service(lifecycle, tuple(sys.argv[1:]))
        else:
            result = run_foreground_service(
                lifecycle,
                tuple(sys.argv[1:]),
                selected_home=selected_home,
            )
        _exit_on_lifecycle_failure(result)


def _service_options_from_args(
    args: argparse.Namespace,
    *,
    selected_home: Path | None = None,
) -> tuple[str, ...]:
    """Convert supported background start options to the service command."""
    options: list[str] = []
    port = getattr(args, "port", None)
    godot_ws_port = getattr(args, "godot_ws_port", None)
    if port is not None:
        options.extend(("--port", str(port)))
    if godot_ws_port is not None:
        options.extend(("--godot-ws-port", str(godot_ws_port)))
    if getattr(args, "data_home", None) is not None:
        if _is_packaged_cli_runtime():
            raise DataHomeSelectionError(
                "安装版生命周期命令不支持 --data-home；安装版只使用 "
                "${ELFIE_HOME:-~/.elfienest}，需要隔离数据根请使用源码 CLI"
            )
        resolved_home = selected_home or resolve_elfie_home(
            args.data_home,
            invoking_cwd=Path.cwd(),
            runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
            source_root=Path(__file__).resolve().parent.parent,
        )
        options.extend(("--data-home", str(resolved_home)))
    if getattr(args, "lan", False):
        options.append("--lan")
    if getattr(args, "runtime_mode", None) is not None:
        options.extend(("--runtime-mode", args.runtime_mode))
    return tuple(options)


def _is_packaged_cli_runtime() -> bool:
    """Return installed mode from executable provenance, not caller env."""
    return bool(getattr(sys, "frozen", False))


def _db_path_for_command(selected_home: Path | None) -> str:
    """Return the database below the already resolved command target."""
    if selected_home is None:
        return str(get_db_path())
    return str(get_db_path_for_home(selected_home))


def _verify_installed_controller_target(
    lifecycle: LifecycleFacade,
    selected_home: Path,
    *,
    command: str,
    require_controller: bool,
) -> None:
    """Reject installed commands that would observe a different Controller root."""
    try:
        result = lifecycle.controller_request(
            "STATUS",
            expected_data_home=selected_home,
        )
    except RuntimeError as error:
        raise DataHomeSelectionError(
            f"安装版 {command} 被拒绝：Controller 数据根校验失败: {error}"
        ) from error
    if require_controller and result is None:
        raise DataHomeSelectionError(
            f"安装版 {command} 需要当前 ELFIE_HOME 对应的 Controller 正在运行"
        )


def _exit_on_lifecycle_failure(result: ServiceLifecycleResult) -> None:
    """Convert lifecycle failures into a non-zero exit code for scripts."""
    if getattr(result, "status", None) == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
