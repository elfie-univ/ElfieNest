"""按房间、机位和观察者隔离摄像头状态。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Final

MAX_CAMERA_VIEWS: Final = 64
MAX_OBSERVERS: Final = 10
MAX_BED_COUNT: Final = 32
ONLINE_TIMEOUT_SECONDS: Final = 2.5
DEFAULT_ROOM_ID: Final = "default"


@dataclass
class _Frame:
    data: bytes = b""
    version: int = 0
    updated_at: float = 0.0


@dataclass
class _RoomState:
    labels: tuple[str, ...] = ()
    active_index: int = 0
    desired_bed_count: int = 4
    reported_bed_count: int | None = None
    frames: dict[int, _Frame] = field(default_factory=dict)
    observers: dict[int, int] = field(default_factory=dict)


class CameraFeedStore:
    """保存房间机位帧，并让每个登录用户独立选择观察机位。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: dict[str, _RoomState] = {}

    def update_frame(
        self,
        frame: bytes,
        active_index: int,
        room_id: str = DEFAULT_ROOM_ID,
        camera_id: int | None = None,
    ) -> None:
        """写入指定房间机位的最新帧。"""
        with self._lock:
            room = self._room(room_id)
            index = self._bounded_index(room, active_index)
            target = index if camera_id is None else camera_id
            snapshot = room.frames.setdefault(target, _Frame())
            snapshot.data = frame
            snapshot.version += 1
            snapshot.updated_at = time.time()
            room.active_index = index

    def update_status(
        self,
        labels: list[str],
        active_index: int,
        bed_count: int,
        room_id: str = DEFAULT_ROOM_ID,
    ) -> None:
        """更新房间机位目录和布局同步状态。"""
        normalized = tuple(str(label).strip() for label in labels if str(label).strip())
        with self._lock:
            room = self._room(room_id)
            room.labels = normalized[:MAX_CAMERA_VIEWS]
            room.active_index = self._bounded_index(room, active_index)
            room.reported_bed_count = bed_count

    def set_desired_bed_count(
        self, bed_count: int, room_id: str = DEFAULT_ROOM_ID
    ) -> None:
        """设置指定房间希望 Godot 重建的床位数量。"""
        with self._lock:
            self._room(room_id).desired_bed_count = max(
                1, min(MAX_BED_COUNT, int(bed_count))
            )

    def select_view(self, index: int, user_id: int, room_id: str = DEFAULT_ROOM_ID) -> None:
        """记录某个用户在某个房间的独立机位选择。"""
        with self._lock:
            room = self._room(room_id)
            if room.labels and not 0 <= index < len(room.labels):
                raise ValueError("摄像头索引超出范围")
            if not room.labels and index != 0:
                raise ValueError("Godot 尚未上报摄像头目录")
            if user_id not in room.observers and len(room.observers) >= MAX_OBSERVERS:
                raise ValueError("一个精灵巢最多支持 10 个观察者")
            room.observers[user_id] = index

    def control(self, room_id: str = DEFAULT_ROOM_ID) -> dict[str, Any]:
        """返回 Godot 需要满足的全部观察者机位目标。"""
        with self._lock:
            room = self._room(room_id)
            views = [
                {"user_id": user_id, "view_index": index}
                for user_id, index in sorted(room.observers.items())
            ]
            default_index = views[0]["view_index"] if views else room.active_index
            return {
                "view_index": default_index,
                "bed_count": room.desired_bed_count,
                "views": views,
            }

    def status(
        self,
        room_id: str = DEFAULT_ROOM_ID,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """返回房间状态，desired_index 按用户隔离。"""
        with self._lock:
            room = self._room(room_id)
            desired_index = room.observers.get(user_id, room.active_index)
            frame = room.frames.get(desired_index)
            age = (
                time.time() - frame.updated_at
                if frame is not None and frame.updated_at
                else None
            )
            return {
                "online": age is not None and age <= ONLINE_TIMEOUT_SECONDS,
                "labels": list(room.labels),
                "active_index": room.active_index,
                "desired_index": desired_index,
                "frame_version": frame.version if frame is not None else 0,
                "updated_at": frame.updated_at if frame is not None else None,
                "desired_bed_count": room.desired_bed_count,
                "reported_bed_count": room.reported_bed_count,
                "layout_syncing": room.reported_bed_count != room.desired_bed_count,
            }

    def frame(
        self,
        room_id: str = DEFAULT_ROOM_ID,
        user_id: int | None = None,
    ) -> tuple[bytes, int]:
        """读取用户当前选择机位的最新帧。"""
        with self._lock:
            room = self._room(room_id)
            index = room.observers.get(user_id, room.active_index)
            snapshot = room.frames.get(index, _Frame())
            return snapshot.data, snapshot.version

    def _room(self, room_id: str) -> _RoomState:
        return self._rooms.setdefault(room_id, _RoomState())

    @staticmethod
    def _bounded_index(room: _RoomState, index: int) -> int:
        if not room.labels:
            return 0
        return max(0, min(len(room.labels) - 1, int(index)))
