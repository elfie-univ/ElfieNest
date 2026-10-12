"""Elfie Lab 静态资源与可选 Godot Web 导出的挂载边界。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from devtools.web_host import mount_vite_bundle


class NoStoreStaticFiles(StaticFiles):
    """Serve rebuildable development assets without browser persistence."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def mount_static_surfaces(app: FastAPI) -> None:
    """挂载 Lab 前端，并在已构建时挂载 Godot Web 导出。"""
    mount_vite_bundle(app)
    godot_web_dir = Path(__file__).parents[2] / "build" / "components" / "godot-web"
    if godot_web_dir.is_dir():
        app.mount(
            "/godot-web",
            NoStoreStaticFiles(directory=godot_web_dir, html=True),
            name="elfie_lab_godot_web",
        )
