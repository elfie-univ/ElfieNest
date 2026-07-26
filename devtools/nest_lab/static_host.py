"""Static hosting boundary for the Nest Lab and optional Godot Web export."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from devtools.web_host import mount_vite_bundle


class NoStoreStaticFiles(StaticFiles):
    """Serve rebuildable Lab assets without browser persistence."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def mount_static_surfaces(app: FastAPI) -> bool:
    """Mount Lab assets and the existing exported Godot bundle when available."""
    mount_vite_bundle(app)
    bundle_dir = Path(__file__).parents[2] / "build" / "components" / "godot-web"
    bundle_ready = (bundle_dir / "elfienest.html").is_file()
    if bundle_ready:
        app.mount(
            "/godot-web",
            NoStoreStaticFiles(directory=bundle_dir, html=True),
            name="nest_lab_godot_web",
        )
    return bundle_ready
