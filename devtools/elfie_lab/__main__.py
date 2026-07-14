"""`.venv/bin/python -m devtools.elfie_lab` 启动入口。"""

import argparse

import uvicorn

from devtools.elfie_lab.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="启动单精灵开发者调试平台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8877, type=int)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--runtime-config-dir", default=None)
    args = parser.parse_args()
    uvicorn.run(
        create_app(args.data_dir, args.runtime_config_dir),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
