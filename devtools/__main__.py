"""Developer Tool unified entry point."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from secrets import token_urlsafe

import uvicorn

from devtools.elfie_lab.host import loopback_host
from devtools.entrypoint import available_tools, resolve_tool
from devtools.lab_restart import (
    ForeignPortOwnerError,
    RestartTimeoutError,
    restart_default_lab,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="developer.sh",
        description="ElfieNest Developer Tool — Module isolation development and debugging platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s elfie-lab                    # Single-elfie debugging (default port 9001)
  %(prog)s elfie-lab --port 8080        # Use custom port
  %(prog)s nest-lab                     # Godot room experiments (default HTTP 9002, WS 9003)
  %(prog)s runtime-lab                  # Configure AI models (interactive TUI)

Documentation: https://elfienest.dev/developer/devtools
""",
    )
    subparsers = parser.add_subparsers(dest="tool", title="Available tools")

    for tool in available_tools():
        subparser = subparsers.add_parser(
            tool.name,
            help=_help_text(tool.name),
            description=_help_description(tool.name),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        if tool.name == "runtime-lab":
            subparser.epilog = """
Runtime Lab is an interactive TUI menu with the following features:

  1. Runtime overview and reports
  2. Provider and model configuration
  3. Agent capability validation
  4. Food strategy configuration

Example:
  %(prog)s runtime-lab

After launch, use arrow keys to navigate and Enter to select.

Data directory: ~/.elfienest-dev/runtime_lab/
"""
            continue
        if tool.default_port is not None:
            host_type = loopback_host
            subparser.add_argument(
                "--host",
                default="127.0.0.1",
                type=host_type,
                help="Bind host address (loopback only, default: 127.0.0.1)",
            )
            subparser.add_argument(
                "--port",
                default=tool.default_port,
                type=int,
                help=f"HTTP service port (default: {tool.default_port})",
            )
            subparser.add_argument(
                "--data-dir",
                default=None,
                help="Data directory (default: ~/.elfienest-dev/<lab-name>)",
            )
            if tool.name == "nest-lab":
                subparser.add_argument(
                    "--godot-ws-port",
                    default=None,
                    type=int,
                    help="Godot WebSocket port (default: HTTP port + 1)",
                )
    return parser


def _help_text(name: str) -> str:
    descriptions = {
        "elfie-lab": "Single-elfie perception and decision debugging (Web UI)",
        "runtime-lab": "Provider and model configuration (interactive TUI)",
        "nest-lab": "Nest/Godot module experiments (Web UI)",
    }
    return descriptions[name]


def _help_description(name: str) -> str:
    descriptions = {
        "elfie-lab": """
Elfie Lab — Single Elfie Debugging Platform

Provides single-elfie profile, perception, decision, chat and turn debugging.
Automatically opens browser interface on startup.

Data directory: ~/.elfienest-dev/elfie_lab/
Default port: 9001
""",
        "runtime-lab": """
Runtime Lab — Provider, Model and Food Configuration TUI

Interactive menu interface for configuring and testing AI model providers
(Ollama, OpenAI, Anthropic, etc.).
Supports three-layer validation: Provider connection, Agent capabilities, Food strategy.

Data directory: ~/.elfienest-dev/runtime_lab/
""",
        "nest-lab": """
Nest Lab — Godot Room and Character Experiments

Provides fixed rooms, temporary characters, path planning and collision experiments.
Automatically opens browser interface and connects to Godot Runtime on startup.

Data directory: ~/.elfienest-dev/nest_lab/
Default ports: HTTP 9002, Godot WebSocket 9003
""",
    }
    return descriptions[name]


def _run_nest_lab(args: argparse.Namespace) -> int:
    from devtools.nest_lab.app import create_app

    tool = resolve_tool("nest-lab")
    data_dir = Path(args.data_dir) if args.data_dir else tool.data_root
    godot_ws_port = args.godot_ws_port or args.port + 1
    browser_url = _browser_url(args.host, args.port)

    def open_browser() -> None:
        webbrowser.open(browser_url)

    uvicorn.run(
        create_app(
            data_dir,
            http_port=args.port,
            godot_ws_port=godot_ws_port,
            on_ready=open_browser,
        ),
        host=args.host,
        port=args.port,
        access_log=False,
    )
    return 0


def _run_elfie_lab(args: argparse.Namespace) -> int:
    from devtools.elfie_lab.app import create_app

    tool = resolve_tool("elfie-lab")
    data_dir = Path(args.data_dir) if args.data_dir else tool.data_root
    browser_url = _browser_url(args.host, args.port)

    def open_browser() -> None:
        webbrowser.open(browser_url)

    uvicorn.run(
        create_app(str(data_dir), on_ready=open_browser),
        host=args.host,
        port=args.port,
        access_log=False,
    )
    return 0


def _browser_url(host: str, port: int) -> str:
    """Use a new local URL for each launch so old Lab shells cannot be reused."""
    return f"http://{host}:{port}/?run={token_urlsafe(12)}"


def _has_explicit_port_override(raw_args: list[str]) -> bool:
    """判断调用方是否明确请求了非默认的网页端口组合。"""
    return any(
        argument in {"--port", "--godot-ws-port"}
        or argument.startswith("--port=")
        or argument.startswith("--godot-ws-port=")
        for argument in raw_args
    )


def _restart_default_lab_if_requested(
    args: argparse.Namespace, raw_args: list[str]
) -> None:
    """默认启动是同类 Lab 的重启；显式端口保留并行实验语义。"""
    if args.tool not in {"elfie-lab", "nest-lab"}:
        return
    if _has_explicit_port_override(raw_args):
        return
    tool = resolve_tool(args.tool)
    workspace = Path(__file__).resolve().parents[1]
    restart_default_lab(tool, workspace)


def main(argv: list[str] | None = None) -> int:
    """展示或启动开发者工具；不会启动普通用户服务。"""
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if raw_args and raw_args[0] == "runtime-lab":
        from devtools.runtime_lab.__main__ import main as runtime_lab_main

        return runtime_lab_main()
    args = _parser().parse_args(raw_args)
    if args.tool is None:
        _parser().print_help()
        return 0
    try:
        _restart_default_lab_if_requested(args, raw_args)
    except (ForeignPortOwnerError, RestartTimeoutError) as error:
        _parser().error(str(error))
    if args.tool == "nest-lab":
        return _run_nest_lab(args)
    if args.tool == "elfie-lab":
        return _run_elfie_lab(args)
    if args.tool == "runtime-lab":
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
