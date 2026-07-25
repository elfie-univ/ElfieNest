"""Elfie Lab 静态资源与可选 Godot Web 导出的挂载边界。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope


class NoStoreStaticFiles(StaticFiles):
    """Serve rebuildable development assets without browser persistence."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def no_store_file_response(path: Path) -> FileResponse:
    """Return an HTML shell response that cannot be reused after a Lab restart."""
    response = FileResponse(path)
    response.headers["Cache-Control"] = "no-store"
    return response


def mount_static_surfaces(app: FastAPI) -> Path:
    """挂载 Lab 前端，并在已构建时挂载 Godot Web 导出。"""
    static_dir = Path(__file__).with_name("static")
    app.mount(
        "/static",
        NoStoreStaticFiles(directory=static_dir),
        name="elfie_lab_static",
    )
    godot_web_dir = Path(__file__).parents[2] / "build" / "components" / "godot-web"
    if godot_web_dir.is_dir():
        app.mount(
            "/godot-web",
            NoStoreStaticFiles(directory=godot_web_dir, html=True),
            name="elfie_lab_godot_web",
        )
    return static_dir
