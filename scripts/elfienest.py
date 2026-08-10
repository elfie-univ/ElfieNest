from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn

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

from ai_runtime.storage.data_home import (
    DataHomeSelectionError,
    get_db_path,
    resolve_elfie_home,
)
from app.bootstrap.accounts import build_accounts_service
from app.bootstrap.lifecycle import create_lifecycle_facade
from app.bootstrap.operations import build_operations_facade
from app.interfaces.cli.doctor_commands import run_doctor
from app.interfaces.cli.foreground_runtime import run_foreground_service
from app.interfaces.cli.lifecycle_commands import (
    default_service_command,
    open_web_console,
    restart_background_service,
    show_service_status,
    start_background_service,
    start_desktop_application,
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
from app.interfaces.cli.tui.common import print_banner
from app.interfaces.cli.tui.config_app import run_config_tui
from app.interfaces.cli.uninstall_commands import run_uninstall_menu
from app.orchestration.lifecycle import LifecycleFacade, ServiceLifecycleResult

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


def main() -> None:
    parser = SecretSafeArgumentParser(
        prog="elfienest",
        description="ElfieNest CLI - Embodied AI Creature System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="commands",
        parser_class=SecretSafeArgumentParser,
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

    serve_parser = subparsers.add_parser(
        "serve", help="Run service in foreground (dev mode)"
    )
    serve_parser.add_argument("--fallback", action="store_true")
    serve_parser.add_argument("--force", action="store_true")
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--ws-port", type=int, default=None)
    serve_parser.add_argument("--godot-ws-port", type=int, default=None)
    serve_parser.add_argument("--no-seed-elfie", action="store_true")
    serve_parser.add_argument("--data-home", default=None)

    start_parser = subparsers.add_parser("start", help="Start background service")
    start_parser.add_argument("--port", type=int, default=None)
    start_parser.add_argument("--ws-port", type=int, default=None)
    start_parser.add_argument("--godot-ws-port", type=int, default=None)
    start_parser.add_argument("--fallback", action="store_true")
    start_parser.add_argument("--no-seed-elfie", action="store_true")
    start_parser.add_argument("--data-home", default=None)
    start_parser.add_argument("--owner-id", default="cli", help=argparse.SUPPRESS)
    start_network_group = start_parser.add_mutually_exclusive_group()
    start_network_group.add_argument(
        "--lan",
        dest="lan",
        action="store_true",
        default=True,
        help="Allow LAN access (default for background start)",
    )
    start_network_group.add_argument(
        "--loopback",
        dest="lan",
        action="store_false",
        help="Bind to loopback only",
    )
    status_parser = subparsers.add_parser("status", help="Show service status")
    status_parser.add_argument(
        "--json", action="store_true", help="Output component health JSON"
    )
    subparsers.add_parser("web", help="Ensure service running and open Web console")
    subparsers.add_parser("desktop", help="Launch packaged ElfieNest Desktop")
    subparsers.add_parser("mobile", help="Show mobile access URL and QR code")
    stop_parser = subparsers.add_parser("stop", help="Stop service")
    stop_parser.add_argument("--owner-id", default="cli", help=argparse.SUPPRESS)
    subparsers.add_parser("restart", help="Force restart service")
    subparsers.add_parser("owner", help="Owner account menu")
    doctor_parser = subparsers.add_parser(
        "doctor", help="Run local diagnostics and config check"
    )
    doctor_parser.add_argument(
        "--fix-ports",
        action="store_true",
        help="Detect and clean up occupied service ports",
    )
    doctor_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts when cleaning ports",
    )
    subparsers.add_parser("uninstall", help="Uninstall and data cleanup")
    subparsers.add_parser("version", help="Show version")
    subparsers.add_parser("setup", help="First-time setup wizard")
    db_parser = subparsers.add_parser("db", help="Database tools")
    db_parser.add_argument(
        "db_command", nargs="?", choices=["backup", "reset"], help="Database command"
    )

    args = parser.parse_args()
    dispatch_command(args, create_lifecycle_facade())


def dispatch_command(
    args: argparse.Namespace, lifecycle: LifecycleFacade | None = None
) -> None:
    lifecycle_client = lifecycle or create_lifecycle_facade()
    try:
        _dispatch_command(args, lifecycle_client)
    except DataHomeSelectionError as error:
        sys.stderr.write(f"elfienest: {error}\n")
        raise SystemExit(2) from error
    except KeyboardInterrupt as error:
        print()
        print("  Cancelled.")
        raise SystemExit(130) from error


def _dispatch_command(args: argparse.Namespace, lifecycle: LifecycleFacade) -> None:
    if args.command == "config":
        run_config_tui(login_provider, getattr(args, "config_path", None))
    elif args.command == "serve":
        options = _service_options_from_args(args)
        if args.force:
            options += ("--force",)
        _exit_on_lifecycle_failure(run_foreground_service(lifecycle, options))
    elif args.command == "status":
        show_service_status(lifecycle, json_output=getattr(args, "json", False))
    elif args.command == "web":
        _exit_on_lifecycle_failure(open_web_console(lifecycle))
    elif args.command == "desktop":
        _exit_on_lifecycle_failure(start_desktop_application(lifecycle))
    elif args.command == "mobile":
        raise SystemExit(show_mobile_access(lifecycle))
    elif args.command == "start":
        command = default_service_command(_service_options_from_args(args))
        owner_id = getattr(args, "owner_id", None)
        _exit_on_lifecycle_failure(
            start_background_service(
                lifecycle,
                command,
                **({"owner_id": owner_id} if owner_id is not None else {}),
            )
        )
    elif args.command == "stop":
        owner_id = getattr(args, "owner_id", None)
        result = (
            stop_background_service(lifecycle, owner_id=owner_id)
            if owner_id is not None
            else stop_background_service(lifecycle)
        )
        _exit_on_lifecycle_failure(result)
    elif args.command == "restart":
        _exit_on_lifecycle_failure(restart_background_service(lifecycle))
    elif args.command == "owner":
        owner_db_path = str(get_db_path())
        raise SystemExit(
            run_owner_menu(
                lifecycle,
                build_accounts_service(owner_db_path),
                owner_db_path,
            )
        )
    elif args.command == "doctor":
        fix_ports = getattr(args, "fix_ports", False)
        force = getattr(args, "force", False)
        if fix_ports:
            from app.interfaces.cli.doctor_commands import run_doctor_with_port_fix

            raise SystemExit(
                run_doctor_with_port_fix(lifecycle, fix_ports=True, force=force)
            )
        else:
            raise SystemExit(run_doctor())
    elif args.command == "uninstall":
        raise SystemExit(run_uninstall_menu())
    elif args.command == "version":
        show_version()
    elif args.command == "setup":
        from app.interfaces.cli.tui.setup_app import run_setup_wizard

        run_setup_wizard()
    elif args.command == "db":
        dispatch_db(
            build_operations_facade(str(get_db_path())),
            getattr(args, "db_command", None),
        )
    else:
        print_banner()
        print("  Starting service...")
        print()
        _exit_on_lifecycle_failure(
            run_foreground_service(lifecycle, tuple(sys.argv[1:]))
        )


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
    if getattr(args, "data_home", None) is not None:
        selected_home = resolve_elfie_home(
            args.data_home,
            invoking_cwd=Path.cwd(),
            runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
            source_root=Path(__file__).resolve().parent.parent,
        )
        options.extend(("--data-home", str(selected_home)))
    if getattr(args, "lan", False):
        options.append("--lan")
    return tuple(options)


def _exit_on_lifecycle_failure(result: ServiceLifecycleResult) -> None:
    """Convert lifecycle failures into a non-zero exit code for scripts."""
    if getattr(result, "status", None) == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
