"""Developer Tool 统一入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from devtools.entrypoint import available_tools, resolve_tool


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ElfieNest Developer Tool")
    subparsers = parser.add_subparsers(dest="tool")
    for tool in available_tools():
        subparser = subparsers.add_parser(tool.name, help=_help_text(tool.name))
        if tool.name == "runtime-lab":
            subparser.add_argument("runtime_args", nargs=argparse.REMAINDER)
            continue
        if tool.default_port is not None:
            subparser.add_argument("--host", default="127.0.0.1")
            subparser.add_argument("--port", default=tool.default_port, type=int)
            subparser.add_argument("--data-dir", default=None)
    return parser


def _help_text(name: str) -> str:
    descriptions = {
        "elfie-lab": "单精灵感知与决策调试",
        "runtime-lab": "Provider 与模型连接实验",
        "nest-lab": "精灵巢/Godot 模块实验",
    }
    return descriptions[name]


def _run_nest_lab(args: argparse.Namespace) -> int:
    from devtools.nest_lab.app import create_app

    tool = resolve_tool("nest-lab")
    data_dir = Path(args.data_dir) if args.data_dir else tool.data_root
    uvicorn.run(create_app(data_dir), host=args.host, port=args.port)
    return 0


def _run_elfie_lab(args: argparse.Namespace) -> int:
    from devtools.elfie_lab.app import create_app

    tool = resolve_tool("elfie-lab")
    data_dir = Path(args.data_dir) if args.data_dir else tool.data_root
    uvicorn.run(create_app(str(data_dir)), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    """展示或启动开发者工具；不会启动普通用户服务。"""
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if raw_args and raw_args[0] == "runtime-lab":
        from devtools.runtime_lab.__main__ import main as runtime_lab_main

        return runtime_lab_main(raw_args[1:])
    args = _parser().parse_args(raw_args)
    if args.tool is None:
        _parser().print_help()
        return 0
    if args.tool == "nest-lab":
        return _run_nest_lab(args)
    if args.tool == "elfie-lab":
        return _run_elfie_lab(args)
    if args.tool == "runtime-lab":
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
