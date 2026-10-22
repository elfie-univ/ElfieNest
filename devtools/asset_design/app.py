"""Serve the approved asset UI without experiment or Godot lifecycle ownership."""

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse

from devtools.asset_design.catalog import (
    ASSET_ROOT,
    Catalog,
    load_catalog,
    registered_file,
)
from devtools.asset_design.cleanup import build_cleanup_router
from devtools.asset_design.design import build_design_router
from devtools.asset_design.glb_resources import RESOURCE_DIRECTORY, RESOURCE_NAME
from devtools.elfie_lab.host import LoopbackHostMiddleware

WEB_ROOT = Path(__file__).parent / "web"
THREE_ROOT = Path(__file__).parents[1] / "web" / "node_modules" / "three"
PREFIX = "/assets/design"
NO_STORE = {"Cache-Control": "no-store"}
PAGES = {
    name: WEB_ROOT / name
    for name in (
        "index.html",
        "library.css",
        "library.js",
        "viewer.html",
        "viewer.css",
        "controls.css",
        "viewer.js",
        "view-state.mjs",
        "asset-media.mjs",
        "cleanup-state.mjs",
        "design-state.mjs",
        "content-images.mjs",
        "catalog-request.mjs",
        "scene-model.mjs",
        "courtyard-detail.mjs",
        "adaptive-detail.mjs",
        "preview-lifecycle.mjs",
        "preview-policy.mjs",
        "authored-appearance.mjs",
        "light-shader-loops.mjs",
        "fixture-lights.mjs",
        "interior-camera.mjs",
    )
}
LIBRARIES = {
    "library/three.module.js": "build/three.module.js",
    "library/three.core.js": "build/three.core.js",
    "library/OrbitControls.js": "examples/jsm/controls/OrbitControls.js",
    "library/GLTFLoader.js": "examples/jsm/loaders/GLTFLoader.js",
    "library/meshopt_simplifier.module.js": "examples/jsm/libs/meshopt_simplifier.module.js",
    "utils/BufferGeometryUtils.js": "examples/jsm/utils/BufferGeometryUtils.js",
    "utils/SkeletonUtils.js": "examples/jsm/utils/SkeletonUtils.js",
}


def build_router(asset_root: Path = ASSET_ROOT) -> APIRouter:
    """Serve the fixed full-page surface in the independent asset workbench."""
    router = APIRouter(prefix=PREFIX)

    @router.get("", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(PAGES["index.html"], headers=NO_STORE)

    @router.get("/catalog.json", response_model=Catalog)
    def catalog(request: Request) -> Response:
        data = load_catalog(asset_root).model_dump_json().encode()
        etag = '"' + hashlib.sha256(data).hexdigest() + '"'
        headers = {"Cache-Control": "no-cache", "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(data, media_type="application/json", headers=headers)

    @router.get("/files/{relative:path}", include_in_schema=False)
    def asset_file(
        relative: str, download: Optional[str] = Query(None)
    ) -> FileResponse:
        file = registered_file(asset_root, relative)
        if file is None:
            raise HTTPException(404, "Saved asset unavailable")
        immutable = Path(
            relative
        ).parent == RESOURCE_DIRECTORY and RESOURCE_NAME.fullmatch(file.name)
        headers = (
            {"Cache-Control": "private, max-age=31536000, immutable"}
            if immutable
            else NO_STORE
        )
        return FileResponse(
            file, headers=headers, filename=file.name if download == "1" else None
        )

    @router.get("/{relative:path}", include_in_schema=False)
    def static_file(relative: str) -> FileResponse:
        file = PAGES.get(relative)
        if relative in LIBRARIES:
            file = THREE_ROOT / LIBRARIES[relative]
        if file is None or not file.is_file():
            raise HTTPException(404, "Workbench resource unavailable")
        return FileResponse(file, headers=NO_STORE)

    return router


def create_app(asset_root: Path = ASSET_ROOT) -> FastAPI:
    """Construct only an asset HTTP service; never load experiment data or engines."""
    app = FastAPI(title="ElfieNest 房屋资产设计")
    app.add_middleware(LoopbackHostMiddleware)
    app.include_router(build_design_router(asset_root))
    app.include_router(build_router(asset_root))
    app.include_router(build_cleanup_router(asset_root))

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse(PREFIX)

    return app
