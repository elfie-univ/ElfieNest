"""Godot 摄像头实时帧中继与已登录用户控制接口。"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Final

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .user_routes import get_current_user

MAX_FRAME_BYTES: Final = 2 * 1024 * 1024
MAX_CAMERA_VIEWS: Final = 64
MAX_BED_COUNT: Final = 32
ONLINE_TIMEOUT_SECONDS: Final = 2.5
LOCAL_CLIENTS: Final = frozenset({"127.0.0.1", "::1", "testclient"})

godot_router = APIRouter(prefix="/api/godot-camera", tags=["godot-camera"])
viewer_router = APIRouter(prefix="/api/camera", tags=["camera"])
RequireUser = Depends(get_current_user)


class CameraFeedStore:
    """在线程间保存最新 JPEG 帧、摄像头目录和待执行选择。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame = b""
        self._frame_version = 0
        self._frame_updated_at = 0.0
        self._labels: tuple[str, ...] = ()
        self._active_index = 0
        self._desired_index = 0
        self._desired_bed_count = 4
        self._reported_bed_count: int | None = None

    def update_frame(self, frame: bytes, active_index: int) -> None:
        with self._lock:
            self._frame = frame
            self._frame_version += 1
            self._frame_updated_at = time.time()
            self._active_index = self._bounded_index(active_index)

    def update_status(
        self,
        labels: list[str],
        active_index: int,
        bed_count: int,
    ) -> None:
        normalized = tuple(str(label).strip() for label in labels if str(label).strip())
        with self._lock:
            self._labels = normalized[:MAX_CAMERA_VIEWS]
            self._active_index = self._bounded_index(active_index)
            self._desired_index = self._bounded_index(self._desired_index)
            self._reported_bed_count = bed_count

    def set_desired_bed_count(self, bed_count: int) -> None:
        with self._lock:
            self._desired_bed_count = max(1, min(MAX_BED_COUNT, int(bed_count)))

    def select_view(self, index: int) -> None:
        with self._lock:
            if not self._labels:
                if index != 0:
                    raise ValueError("Godot 尚未上报摄像头目录")
            elif index < 0 or index >= len(self._labels):
                raise ValueError("摄像头索引超出范围")
            self._desired_index = index

    def control(self) -> Dict[str, int]:
        with self._lock:
            return {
                "view_index": self._desired_index,
                "bed_count": self._desired_bed_count,
            }

    def status(self) -> Dict[str, Any]:
        with self._lock:
            age = time.time() - self._frame_updated_at if self._frame_updated_at else None
            return {
                "online": age is not None and age <= ONLINE_TIMEOUT_SECONDS,
                "labels": list(self._labels),
                "active_index": self._active_index,
                "desired_index": self._desired_index,
                "frame_version": self._frame_version,
                "updated_at": self._frame_updated_at or None,
                "desired_bed_count": self._desired_bed_count,
                "reported_bed_count": self._reported_bed_count,
                "layout_syncing": self._reported_bed_count != self._desired_bed_count,
            }

    def frame(self) -> tuple[bytes, int]:
        with self._lock:
            return self._frame, self._frame_version

    def _bounded_index(self, index: int) -> int:
        if not self._labels:
            return 0
        return max(0, min(len(self._labels) - 1, int(index)))


def _feed(request: Request) -> CameraFeedStore:
    return request.app.state.camera_feed


def _require_local_client(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in LOCAL_CLIENTS:
        raise HTTPException(status_code=403, detail="摄像头上报接口仅允许本机访问")


@godot_router.post("/frame")
async def publish_camera_frame(request: Request, view_index: int = 0) -> Dict[str, int]:
    _require_local_client(request)
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(status_code=415, detail="摄像头帧必须为 image/jpeg")
    frame = await request.body()
    if not frame or len(frame) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="摄像头帧为空或超过 2 MiB")
    if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
        raise HTTPException(status_code=422, detail="摄像头帧不是有效 JPEG")
    feed = _feed(request)
    feed.update_frame(frame, view_index)
    return {"frame_version": feed.status()["frame_version"]}


@godot_router.post("/status")
async def publish_camera_status(body: Dict[str, Any], request: Request) -> Dict[str, Any]:
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
    _feed(request).update_status(labels, active_index, bed_count)
    return {"detail": "Camera status updated"}


@godot_router.get("/control")
async def get_camera_control(request: Request) -> Dict[str, int]:
    _require_local_client(request)
    return _feed(request).control()


@viewer_router.get("/status")
async def get_camera_status(
    request: Request,
    user: Dict[str, Any] = RequireUser,
) -> Dict[str, Any]:
    _ = user
    return _feed(request).status()


@viewer_router.get("/frame.jpg")
async def get_camera_frame(
    request: Request,
    user: Dict[str, Any] = RequireUser,
) -> Response:
    _ = user
    frame, version = _feed(request).frame()
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
    _ = user
    try:
        index = int(body.get("index"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="index 必须是整数") from exc
    try:
        _feed(request).select_view(index)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"view_index": index}
