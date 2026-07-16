"""``python -m devtools.nest_lab`` 启动入口。"""

from __future__ import annotations

import argparse

import uvicorn

from devtools.nest_lab.app import create_app


def main() -> None:
    """启动独立的精灵巢模块实验台。"""
    parser = argparse.ArgumentParser(description="启动精灵巢模块 Developer Tool")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8890, type=int)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
