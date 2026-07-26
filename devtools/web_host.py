"""Shared Vite bundle hosting for browser-based Developer Tools."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from scripts.build_devtools_web import OUTPUT_DIRECTORY, ensure_bundle

LabShell = Literal["elfie", "nest"]


class NoStoreStaticFiles(StaticFiles):
    """Serve rebuildable developer assets without browser persistence."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def mount_vite_bundle(app: FastAPI) -> Path:
    """Mount the current shared Vite output under the stable `/ui` prefix."""
    bundle_dir = ensure_bundle()
    app.mount("/ui", NoStoreStaticFiles(directory=bundle_dir), name="devtools_web")
    return bundle_dir


def frontend_shell(lab: LabShell, bundle_dir: Path = OUTPUT_DIRECTORY) -> HTMLResponse:
    """Return the Vite HTML shell with the Lab identity injected at the boundary."""
    shell = (bundle_dir / "index.html").read_text(encoding="utf-8")
    marker = 'window.__ELFIENEST_LAB__ = "__ELFIENEST_LAB__"'
    if marker not in shell:
        raise RuntimeError("Developer Tools Web 页面缺少 Lab 入口标记")
    response = HTMLResponse(
        shell.replace(marker, f'window.__ELFIENEST_LAB__ = "{lab}"')
    )
    response.headers["Cache-Control"] = "no-store"
    return response
