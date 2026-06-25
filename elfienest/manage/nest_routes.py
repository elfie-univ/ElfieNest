from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from .admin_routes import require_admin
from .store import get_db
from .user_routes import get_current_user

logger = logging.getLogger("elfienest.manage.nest_routes")

router = APIRouter(prefix="/api/admin/nest", tags=["nest"])
user_router = APIRouter(prefix="/api/user/nest", tags=["user-nest"])


def _rooms_with_beds(db_path: str, user_id: int | None = None) -> list[Dict[str, Any]]:
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
                    user_id is not None
                    and bed.get("occupant_owner_user_id") == user_id
                )
                beds.append(bed)
            room["beds"] = beds
        return rooms

@router.get("/rooms")
async def get_rooms(request: Request, admin: Dict[str, Any] = Depends(require_admin)) -> list[Dict[str, Any]]:
    """获取所有房间和床位信息。"""
    _ = admin
    return _rooms_with_beds(request.app.state.db_path)


@user_router.get("/rooms")
async def get_user_rooms(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    return _rooms_with_beds(request.app.state.db_path, user_id=user["id"])

@router.post("/rooms")
async def create_room(body: Dict[str, Any], request: Request, admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """创建一个新房间。"""
    name = body.get("name", "New Room")
    max_capacity = body.get("max_capacity", 4)
    with get_db(request.app.state.db_path) as conn:
        cursor = conn.execute("INSERT INTO rooms (name, max_capacity) VALUES (?, ?)", (name, max_capacity))
        room_id = cursor.lastrowid
        # 默认生成床位
        for i in range(max_capacity):
            conn.execute(
                "INSERT INTO beds (room_id, name, grid_x, grid_y) VALUES (?, ?, ?, ?)",
                (room_id, f"Bed {i+1}", i * 100, 0)
            )
        conn.commit()
        return {"id": room_id, "name": name, "max_capacity": max_capacity}

@router.put("/beds/{bed_id}")
async def update_bed(bed_id: int, body: Dict[str, Any], request: Request, admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
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

@router.put("/elfies/{elfie_id}/bed")
async def assign_bed(elfie_id: str, body: Dict[str, Any], request: Request, admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """为精灵分配床位。"""
    bed_id = body.get("bed_id")  # 可以为 None 以取消分配
    with get_db(request.app.state.db_path) as conn:
        conn.execute("UPDATE elfie_registry SET bed_id = ? WHERE elfie_id = ?", (bed_id, elfie_id))
        conn.commit()
        return {"detail": "Bed assigned"}
