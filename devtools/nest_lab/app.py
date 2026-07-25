"""Isolated interactive Nest/Godot developer laboratory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable, Dict, Union

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from ai_runtime.storage.data_home import get_elfie_developer_home
from devtools.elfie_lab.host import LoopbackHostMiddleware
from devtools.nest_lab.routes import build_router
from devtools.nest_lab.static_host import mount_static_surfaces
from devtools.nest_lab.world import NestLabWorld
from devtools.web_host import frontend_shell


def create_app(
    data_dir: Path | str | None = None,
    *,
    http_port: int = 9002,
    godot_ws_port: int = 9003,
    on_ready: Callable[[], None] | None = None,
) -> FastAPI:
    """Create one disposable Lab without production engine or data dependencies."""
    root = (
        Path(data_dir)
        if data_dir is not None
        else get_elfie_developer_home() / "nest_lab"
    )
    root.mkdir(parents=True, exist_ok=True)
    world = NestLabWorld(
        data_dir=root,
        http_port=http_port,
        websocket_port=godot_ws_port,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        world.start()
        if on_ready is not None:
            on_ready()
        try:
            yield
        finally:
            world.stop()

    app = FastAPI(
        title="ElfieNest Nest Lab",
        description="开发者专用的精灵巢与 Godot Runtime 实验台",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(LoopbackHostMiddleware)
    app.state.data_dir = root
    app.state.world = world
    bundle_ready = mount_static_surfaces(app)
    app.state.godot_web_ready = bundle_ready
    app.include_router(build_router(world))

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        return frontend_shell("nest")

    @app.get("/api/health")
    def health() -> Dict[str, Union[bool, str]]:
        return {
            "status": "ok",
            "service": "nest-lab",
            "scope": "developer",
            "production_engine": False,
        }

    @app.get("/api/godot-web")
    def godot_web_status() -> Dict[str, Union[bool, str]]:
        return {
            "ready": bundle_ready,
            "entry_url": "/godot-web/elfienest.html" if bundle_ready else "",
            "build_command": "./developer.sh build-godot-web",
        }

    return app
