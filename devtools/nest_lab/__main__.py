"""``python -m devtools.nest_lab`` 启动入口。"""

from __future__ import annotations

import argparse
import webbrowser
from secrets import token_urlsafe

import uvicorn

from devtools.elfie_lab.host import loopback_host
from devtools.nest_lab.app import create_app


def main() -> None:
    """启动独立的精灵巢模块实验台。"""
    parser = argparse.ArgumentParser(description="启动精灵巢模块 Developer Tool")
    parser.add_argument("--host", default="127.0.0.1", type=loopback_host)
    parser.add_argument("--port", default=9002, type=int)
    parser.add_argument("--godot-ws-port", default=None, type=int)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    godot_ws_port = args.godot_ws_port or args.port + 1
    browser_url = f"http://{args.host}:{args.port}/?run={token_urlsafe(12)}"

    def open_browser() -> None:
        webbrowser.open(browser_url)

    uvicorn.run(
        create_app(
            args.data_dir,
            http_port=args.port,
            godot_ws_port=godot_ws_port,
            on_ready=open_browser,
        ),
        host=args.host,
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
