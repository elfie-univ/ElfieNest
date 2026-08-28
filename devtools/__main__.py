"""Developer Tool unified entry point."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from secrets import token_urlsafe

import uvicorn

from devtools.elfie_lab.host import loopback_host
from devtools.entrypoint import DeveloperTool, available_tools, resolve_tool
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
  %(prog)s elfie-lab                    # 单精灵实验（HTTP 9001）
  %(prog)s brain-eval                   # 批量评测（HTTP 9001）
  %(prog)s nest-lab                     # 精灵巢实验（HTTP 9001）

Documentation: https://elfienest.dev/developer/engineering/devtools
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
        if tool.name == "brain-eval":
            from devtools.brain_eval.cli import configure_parser

            configure_parser(subparser, action_required=False)
            _add_web_options(subparser, tool)
        elif tool.default_port is not None:
            _add_web_options(subparser, tool)
            if tool.name == "nest-lab":
                subparser.add_argument(
                    "--godot-ws-port",
                    default=None,
                    type=int,
                    help="Godot WebSocket 内部端口（默认：HTTP 端口 + 1）",
                )
    return parser


def _add_web_options(subparser: argparse.ArgumentParser, tool: DeveloperTool) -> None:
    """Add the small optional diagnostics surface shared by all web commands."""
    host_type = loopback_host
    subparser.add_argument(
        "--host",
        default="127.0.0.1",
        type=host_type,
        help="Bind host address (loopback only, default: 127.0.0.1)",
    )
    subparser.add_argument(
        "--port",
        default=tool.default_port or 9001,
        type=int,
        help=f"HTTP service port (default: {tool.default_port or 9001})",
    )
    subparser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory (default: ~/.elfienest-dev)",
    )


def _help_text(name: str) -> str:
    descriptions = {
        "elfie-lab": "打开单精灵实验页面（统一 Developer Tools Web UI）",
        "nest-lab": "打开精灵巢实验页面（统一 Developer Tools Web UI）",
        "brain-eval": "打开批量评测页面（统一 Developer Tools Web UI）",
    }
    return descriptions[name]


def _help_description(name: str) -> str:
    descriptions = {
        "elfie-lab": """
Elfie Lab — Single Elfie Debugging Platform

Provides single-elfie profile, perception, decision, chat and turn debugging.
Automatically opens the single-elfie page in the shared Developer Tools service.

Data directory: ~/.elfienest-dev/elfie_lab/ (inside the shared developer root)
Default HTTP port: 9001
""",
        "nest-lab": """
Nest Lab — Godot Room and Character Experiments

Provides fixed rooms, temporary characters, path planning and collision experiments.
Automatically opens the Nest page in the shared Developer Tools service.

Data directory: ~/.elfienest-dev/nest_lab/ (inside the shared developer root)
Default HTTP port: 9001; Godot WebSocket is an internal port (9002 by default)
""",
        "brain-eval": """
Brain Eval — Reproducible Elfie Brain Evaluation

Opens the batch evaluation page.  The explicit ``catalog``, ``capture``,
``compare`` and ``calibrate`` actions remain available for artifact workflows.

Default HTTP port: 9001
Artifacts: build/brain-eval/<run-id>/ (for explicit actions)
""",
    }
    return descriptions[name]


def _run_nest_lab(args: argparse.Namespace) -> int:
    return _run_unified_lab(args, "experiment", "/nest/experiment")


def _run_elfie_lab(args: argparse.Namespace) -> int:
    return _run_unified_lab(args, "experiment", "/elfie/experiment")


def _run_unified_lab(
    args: argparse.Namespace,
    page: str,
    initial_path: str,
) -> int:
    from devtools.elfie_lab.app import create_unified_app

    data_dir = Path(args.data_dir) if args.data_dir else None
    browser_lab = "nest" if initial_path == "/nest/experiment" else "elfie"
    browser_url = _browser_url(args.host, args.port, browser_lab, page)
    godot_ws_port = getattr(args, "godot_ws_port", None)

    def open_browser() -> None:
        webbrowser.open(browser_url)

    uvicorn.run(
        create_unified_app(
            data_dir,
            http_port=args.port,
            godot_ws_port=godot_ws_port,
            default_path=initial_path,
            on_ready=open_browser,
        ),
        host=args.host,
        port=args.port,
        access_log=False,
    )
    return 0


def _browser_url(
    host: str,
    port: int,
    lab: str = "elfie",
    page: str = "experiment",
) -> str:
    """Use a new local URL for each launch so old Lab shells cannot be reused."""
    path = (
        "/nest/experiment"
        if lab == "nest"
        else ("/elfie/evaluations" if page == "evaluations" else "/elfie/experiment")
    )
    return f"http://{host}:{port}{path}?run={token_urlsafe(12)}"


def _has_explicit_port_override(raw_args: list[str]) -> bool:
    """判断调用方是否明确请求了非默认的网页端口组合。"""
    return any(
        argument in {"--port", "--godot-ws-port"}
        or argument.startswith("--port=")
        or argument.startswith("--godot-ws-port=")
        for argument in raw_args
    )


def _uses_default_lab_ports(args: argparse.Namespace, tool: DeveloperTool) -> bool:
    """判断显式端口参数是否仍指向该 Lab 的默认端口组合。

    显式写出默认端口不应绕过默认实例回收；否则用户重启
    ``developer.sh nest-lab --port 9001 --godot-ws-port 9002`` 时会把旧
    页面继续留在端口上，导致浏览器看到的代码与当前工作树不一致。
    """
    if tool.default_port is None or args.port != tool.default_port:
        return False
    if tool.name == "nest-lab":
        return args.godot_ws_port in (None, args.port + 1)
    return True


def _restart_default_lab_if_requested(
    args: argparse.Namespace, raw_args: list[str]
) -> None:
    """默认启动是同类 Lab 的重启；显式端口保留并行实验语义。"""
    if args.tool not in {"elfie-lab", "nest-lab", "brain-eval"}:
        return
    # ``brain-eval catalog|capture|compare|calibrate`` is still an artifact
    # CLI.  Only the no-action form is the shared web launcher.
    if args.tool == "brain-eval" and getattr(args, "brain_eval_action", None):
        return
    tool = resolve_tool(args.tool)
    if _has_explicit_port_override(raw_args) and not _uses_default_lab_ports(
        args, tool
    ):
        return
    workspace = Path(__file__).resolve().parents[1]
    restart_default_lab(tool, workspace)


def main(argv: list[str] | None = None) -> int:
    """展示或启动开发者工具；不会启动普通用户服务。"""
    raw_args = list(argv) if argv is not None else sys.argv[1:]
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
    if args.tool == "brain-eval":
        if args.brain_eval_action is None:
            return _run_unified_lab(args, "evaluations", "/elfie/evaluations")
        from devtools.brain_eval.cli import run as run_brain_eval

        try:
            return run_brain_eval(args)
        except ValueError as error:
            print(f"brain-eval: invalid input: {error}", file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
