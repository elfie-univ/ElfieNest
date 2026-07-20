"""Godot 摄像头实时帧中继与已登录用户控制接口。"""

from __future__ import annotations

import secrets
from typing import Any, Dict, Final

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.features.accounts.auth import get_current_user
from app.interfaces.api.camera_state import (
    DEFAULT_ROOM_ID,
    MAX_BED_COUNT,
    MAX_CAMERA_VIEWS,
    CameraFeedStore,
)

MAX_FRAME_BYTES: Final = 2 * 1024 * 1024
LOCAL_CLIENTS: Final = frozenset({"127.0.0.1", "::1", "testclient"})

godot_router = APIRouter(prefix="/api/godot-camera", tags=["godot-camera"])
viewer_router = APIRouter(prefix="/api/camera", tags=["camera"])
RequireUser = Depends(get_current_user)


def _feed(request: Request) -> CameraFeedStore:
    return request.app.state.camera_feed


def _require_local_client(request: Request) -> None:
    host = request.client.host if request.client else ""
    expected_token = request.app.state.godot_camera_token
    provided_token = request.headers.get("X-ElfieNest-Godot-Token", "")
    if host not in LOCAL_CLIENTS or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(status_code=403, detail="摄像头上报接口仅允许本机访问")


@godot_router.post("/frame")
async def publish_camera_frame(
    request: Request,
    view_index: int = 0,
    room_id: str = DEFAULT_ROOM_ID,
) -> Dict[str, int]:
    _require_local_client(request)
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(status_code=415, detail="摄像头帧必须为 image/jpeg")
    frame = await request.body()
    if not frame or len(frame) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="摄像头帧为空或超过 2 MiB")
    if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
        raise HTTPException(status_code=422, detail="摄像头帧不是有效 JPEG")
    feed = _feed(request)
    feed.update_frame(frame, view_index, room_id=room_id)
    return {"frame_version": feed.status(room_id=room_id)["frame_version"]}


@godot_router.post("/status")
async def publish_camera_status(
    body: Dict[str, Any], request: Request, room_id: str = DEFAULT_ROOM_ID
) -> Dict[str, Any]:
    _require_local_client(request)
    labels = body.get("labels")
    if not isinstance(labels, list) or len(labels) > MAX_CAMERA_VIEWS:
        raise HTTPException(status_code=422, detail="labels 必须是最多 64 项的数组")
    try:
        active_index = int(body.get("active_index", 0))
        bed_count = int(body.get("bed_count"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="active_index 和 bed_count 必须是整数") from exc
    if bed_count < 1 or bed_count > MAX_BED_COUNT:
        raise HTTPException(status_code=422, detail="bed_count 必须在 1 到 32 之间")
    _feed(request).update_status(labels, active_index, bed_count, room_id=room_id)
    return {"detail": "Camera status updated"}


@godot_router.get("/control")
async def get_camera_control(
    request: Request, room_id: str = DEFAULT_ROOM_ID
) -> Dict[str, Any]:
    _require_local_client(request)
    return _feed(request).control(room_id=room_id)


@viewer_router.get("/status")
async def get_camera_status(
    request: Request,
    user: Dict[str, Any] = RequireUser,
) -> Dict[str, Any]:
    return _feed(request).status(user_id=int(user["id"]))


@viewer_router.get("/frame.jpg")
async def get_camera_frame(
    request: Request,
    user: Dict[str, Any] = RequireUser,
) -> Response:
    frame, version = _feed(request).frame(user_id=int(user["id"]))
    if not frame:
        raise HTTPException(status_code=503, detail="Godot 摄像头尚未提供画面")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Camera-Frame-Version": str(version),
        },
    )


@viewer_router.put("/view")
async def select_camera_view(
    body: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = RequireUser,
) -> Dict[str, int]:
    try:
        index = int(body.get("index"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="index 必须是整数") from exc
    try:
        _feed(request).select_view(index, user_id=int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"view_index": index}
