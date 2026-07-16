"""不依赖正式引擎的精灵巢模块实验服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Union

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from runtime.storage.data_home import get_elfie_home


def create_app(data_dir: Path | str | None = None) -> FastAPI:
    """创建隔离的 Nest Lab 应用，不连接正式数据库或 Godot 服务。"""
    root = Path(data_dir or get_elfie_home() / "developer" / "nest_lab").expanduser()
    root.mkdir(parents=True, exist_ok=True)
    static_dir = Path(__file__).with_name("static")
    app = FastAPI(
        title="ElfieNest Nest Lab",
        description="开发者专用的精灵巢模块实验台",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.data_dir = root
    app.mount("/static", StaticFiles(directory=static_dir), name="nest_lab_static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> Dict[str, Union[bool, str]]:
        return {
            "status": "ok",
            "service": "nest-lab",
            "scope": "developer",
            "production_engine": False,
        }

    @app.get("/api/world")
    def world() -> Dict[str, Union[bool, int, str]]:
        return {
            "module": "elfienest-world",
            "runtime": "isolated",
            "production_engine": False,
            "max_elfies": 32,
            "data_dir": str(root),
        }

    @app.get("/api/agents")
    def agents() -> dict[str, list[dict[str, str]]]:
        return {"items": []}

    return app
