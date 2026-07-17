from __future__ import annotations

import logging
from typing import Any, Dict, Final

from fastapi import APIRouter, Depends, HTTPException, Request

from elfienest.accounts.auth import get_current_user, require_owner
from elfienest.persistence.store import get_db

logger = logging.getLogger("elfienest.api.nest_routes")

router = APIRouter(prefix="/api/owner/nest", tags=["nest"])
user_router = APIRouter(prefix="/api/user/nest", tags=["user-nest"])
RequireOwner = Depends(require_owner)
RequireUser = Depends(get_current_user)
DEFAULT_ROOM_NAME = "Main Nest"
DEFAULT_BED_COUNT = 4
MAX_BED_COUNT: Final = 32
DEFAULT_BED_COLUMNS: Final = 3
DEFAULT_BED_X: Final = (18, 39, 60)
DEFAULT_BED_Y_START: Final = 34
DEFAULT_BED_Y_GAP: Final = 20


def _default_bed_position(index: int) -> tuple[int, int]:
    row = index // DEFAULT_BED_COLUMNS
    column = index % DEFAULT_BED_COLUMNS
    return (DEFAULT_BED_X[column], DEFAULT_BED_Y_START + row * DEFAULT_BED_Y_GAP)


def _ensure_default_room(db_path: str) -> None:
    with get_db(db_path) as conn:
        room = conn.execute("SELECT id FROM rooms ORDER BY id LIMIT 1").fetchone()
        if room is not None:
            return
        cursor = conn.execute(
            "INSERT INTO rooms (name, max_capacity) VALUES (?, ?)",
            (DEFAULT_ROOM_NAME, DEFAULT_BED_COUNT),
        )
        room_id = cursor.lastrowid
        for index in range(DEFAULT_BED_COUNT):
            grid_x, grid_y = _default_bed_position(index)
            conn.execute(
                "INSERT INTO beds (room_id, name, grid_x, grid_y) VALUES (?, ?, ?, ?)",
                (room_id, f"Bed {index + 1}", grid_x, grid_y),
            )
        conn.commit()


def _sync_bed_count(db_path: str, room_id: int, target_count: int) -> dict[str, int]:
    target_count = max(DEFAULT_BED_COUNT, min(MAX_BED_COUNT, target_count))
    with get_db(db_path) as conn:
        room = conn.execute("SELECT id FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")

        rows = conn.execute(
            """
            SELECT b.id, b.name, e.elfie_id AS occupant_id
            FROM beds b
            LEFT JOIN elfie_registry e ON e.bed_id = b.id
            WHERE b.room_id = ?
            ORDER BY b.id
            """,
            (room_id,),
        ).fetchall()
        current_count = len(rows)
        if target_count > current_count:
            for index in range(current_count, target_count):
                grid_x, grid_y = _default_bed_position(index)
                conn.execute(
                    "INSERT INTO beds (room_id, name, grid_x, grid_y) VALUES (?, ?, ?, ?)",
                    (room_id, f"Bed {index + 1}", grid_x, grid_y),
                )
        elif target_count < current_count:
            removable = [
                row["id"] for row in reversed(rows) if row["occupant_id"] is None
            ]
            for bed_id in removable[: current_count - target_count]:
                conn.execute("DELETE FROM beds WHERE id = ?", (bed_id,))

        final_count = conn.execute(
            "SELECT COUNT(*) FROM beds WHERE room_id = ?",
            (room_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE rooms SET max_capacity = ? WHERE id = ?", (final_count, room_id)
        )
        conn.commit()
        return {"bed_count": final_count, "requested_count": target_count}


def _rooms_with_beds(db_path: str, user_id: int | None = None) -> list[Dict[str, Any]]:
    _ensure_default_room(db_path)
    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT * FROM rooms ORDER BY id")
        rooms = [dict(r) for r in cursor.fetchall()]
        for room in rooms:
            cursor = conn.execute(
                """
                SELECT b.*,
                       e.elfie_id AS occupant_id,
                       e.name AS occupant_name,
                       e.owner_user_id AS occupant_owner_user_id,
                       e.anatomy_type AS occupant_anatomy_type,
                       u.username AS occupant_owner_username
                FROM beds b
                LEFT JOIN elfie_registry e ON e.bed_id = b.id
                LEFT JOIN users u ON u.id = e.owner_user_id
                WHERE b.room_id = ?
                ORDER BY b.id
                """,
                (room["id"],),
            )
            beds = []
            for row in cursor.fetchall():
                bed = dict(row)
                bed["occupant_is_mine"] = (
                    user_id is not None and bed.get("occupant_owner_user_id") == user_id
                )
                beds.append(bed)
            room["beds"] = beds
        return rooms


def _publish_desired_layout(request: Request, rooms: list[Dict[str, Any]]) -> None:
    if rooms:
        request.app.state.camera_feed.set_desired_bed_count(len(rooms[0]["beds"]))


def _default_room_id(db_path: str) -> int:
    _ensure_default_room(db_path)
    with get_db(db_path) as conn:
        room = conn.execute("SELECT id FROM rooms ORDER BY id LIMIT 1").fetchone()
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        return int(room["id"])


def _bed_count_from_body(body: Dict[str, Any]) -> int:
    return _bounded_bed_count(body.get("bed_count", DEFAULT_BED_COUNT), "bed_count")


def _bounded_bed_count(value: Any, field_name: str) -> int:
    try:
        requested_count = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail=f"{field_name} must be an integer"
        ) from exc
    return max(DEFAULT_BED_COUNT, min(MAX_BED_COUNT, requested_count))


@router.get("/rooms")
async def get_rooms(
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> list[Dict[str, Any]]:
    """获取所有房间和床位信息。"""
    _ = owner
    rooms = _rooms_with_beds(request.app.state.db_path)
    _publish_desired_layout(request, rooms)
    return rooms


@user_router.get("/rooms")
async def get_user_rooms(
    request: Request,
    user: Dict[str, Any] = RequireUser,
) -> list[Dict[str, Any]]:
    rooms = _rooms_with_beds(request.app.state.db_path, user_id=user["id"])
    _publish_desired_layout(request, rooms)
    return rooms


@router.post("/rooms")
async def create_room(
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Any]:
    """创建一个新房间。"""
    name = body.get("name", "New Room")
    max_capacity = _bounded_bed_count(
        body.get("max_capacity", DEFAULT_BED_COUNT), "max_capacity"
    )
    with get_db(request.app.state.db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO rooms (name, max_capacity) VALUES (?, ?)",
            (name, max_capacity),
        )
        room_id = cursor.lastrowid
        # 默认生成床位
        for i in range(max_capacity):
            conn.execute(
                "INSERT INTO beds (room_id, name, grid_x, grid_y) VALUES (?, ?, ?, ?)",
                (room_id, f"Bed {i + 1}", i * 100, 0),
            )
        conn.commit()
        return {"id": room_id, "name": name, "max_capacity": max_capacity}


@router.put("/beds/{bed_id}")
async def update_bed(
    bed_id: int,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Any]:
    """更新床位坐标。"""
    updates = []
    params = []
    if "grid_x" in body:
        updates.append("grid_x = ?")
        params.append(body["grid_x"])
    if "grid_y" in body:
        updates.append("grid_y = ?")
        params.append(body["grid_y"])

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(bed_id)
    with get_db(request.app.state.db_path) as conn:
        conn.execute(f"UPDATE beds SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return {"detail": "Bed updated"}


@router.put("/rooms/default/bed-count")
async def update_default_room_bed_count(
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, int]:
    _ = owner
    room_id = _default_room_id(request.app.state.db_path)
    target_count = _bed_count_from_body(body)
    result = _sync_bed_count(request.app.state.db_path, room_id, target_count)
    request.app.state.camera_feed.set_desired_bed_count(result["bed_count"])
    return result


@router.put("/rooms/{room_id}/bed-count")
async def update_bed_count(
    room_id: int,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, int]:
    _ = owner
    target_count = _bed_count_from_body(body)
    result = _sync_bed_count(request.app.state.db_path, room_id, target_count)
    if room_id == _default_room_id(request.app.state.db_path):
        request.app.state.camera_feed.set_desired_bed_count(result["bed_count"])
    return result


@router.put("/elfies/{elfie_id}/bed")
async def assign_bed(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Any]:
    """为精灵分配床位。"""
    bed_id = body.get("bed_id")  # 可以为 None 以取消分配
    with get_db(request.app.state.db_path) as conn:
        conn.execute(
            "UPDATE elfie_registry SET bed_id = ? WHERE elfie_id = ?",
            (bed_id, elfie_id),
        )
        conn.commit()
        return {"detail": "Bed assigned"}
