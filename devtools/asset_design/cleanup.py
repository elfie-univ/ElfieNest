"""Preserve review marks and the workbench's recoverable delete action."""

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, StrictBool

from devtools.asset_design.catalog import load_catalog
from devtools.asset_design.deletion import delete_asset
from devtools.asset_design.design import ASSET_LOCK


class MarkChange(BaseModel):
    marked: StrictBool


class Marks(BaseModel):
    markedIds: list[str]


def build_cleanup_router(asset_root: Path) -> APIRouter:
    router = APIRouter(prefix="/assets/cleanup")
    mark_file = asset_root / ".cleanup-marks.json"
    lock = ASSET_LOCK

    def read_marks() -> Marks:
        return (
            Marks.model_validate_json(mark_file.read_text())
            if mark_file.is_file()
            else Marks(markedIds=[])
        )

    @router.get("/marks", response_model=Marks)
    def marks(response: Response) -> Marks:
        response.headers["Cache-Control"] = "no-store"
        with lock:
            return read_marks()

    @router.put("/marks/{asset_id}", response_model=Marks)
    def change_mark(asset_id: str, change: MarkChange, request: Request) -> Marks:
        origin = request.headers.get("origin")
        if (
            origin and origin != str(request.base_url).rstrip("/")
        ) or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Mark assets from this local workbench")
        with lock:
            if not any(
                asset.id == asset_id for asset in load_catalog(asset_root).assets
            ):
                raise HTTPException(404, "Saved asset unavailable")
            ids = set(read_marks().markedIds)
            if change.marked:
                ids.add(asset_id)
            else:
                ids.discard(asset_id)
            result = Marks(markedIds=sorted(ids))
            asset_root.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=asset_root,
                    prefix=".cleanup-",
                    delete=False,
                ) as output:
                    temporary = Path(output.name)
                    json.dump(result.model_dump(), output, ensure_ascii=False, indent=2)
                    output.write("\n")
                os.replace(temporary, mark_file)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return result

    @router.delete("/assets/{asset_id}")
    def remove_asset(asset_id: str, request: Request) -> dict:
        origin = request.headers.get("origin")
        if (
            origin and origin != str(request.base_url).rstrip("/")
        ) or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Delete assets from this local workbench")
        with lock:
            return delete_asset(asset_root, asset_id)

    return router
