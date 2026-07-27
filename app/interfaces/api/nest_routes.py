from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.features.accounts.auth import get_current_user, require_owner
from app.infrastructure.persistence.nest_repository import (
    NestRepositoryConflictError,
    NestRepositoryNotFoundError,
    SQLiteNestRepository,
)
from app.infrastructure.persistence.store import get_db

logger = logging.getLogger("app.interfaces.api.nest_routes")

router = APIRouter(prefix="/api/owner/nest", tags=["nest"])
user_router = APIRouter(prefix="/api/user/nest", tags=["user-nest"])
RequireOwner = Depends(require_owner)
RequireUser = Depends(get_current_user)
DEFAULT_BED_COUNT = 4
MIN_BED_COUNT = 4
MAX_BED_COUNT = 32


def _rooms_with_beds(
    db_path: str,
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    with get_db(db_path) as conn:
        repository = SQLiteNestRepository(conn)
        rooms = repository.load_view().as_rooms_payload(user_id=user_id)
        conn.commit()
        return rooms


def _bed_count_from_body(body: dict[str, Any]) -> int:
    raw_value = body.get("bed_count", DEFAULT_BED_COUNT)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise HTTPException(status_code=422, detail="bed_count must be an integer")
    if not MIN_BED_COUNT <= raw_value <= MAX_BED_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"bed_count 必须在 {MIN_BED_COUNT} 到 {MAX_BED_COUNT} 之间",
        )
    return raw_value


@router.get("/rooms")
async def get_rooms(
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> List[Dict[str, Any]]:
    _ = owner
    rooms = _rooms_with_beds(request.app.state.db_path)
    return rooms


@user_router.get("/rooms")
async def get_user_rooms(
    request: Request,
    user: Dict[str, Any] = RequireUser,
) -> List[Dict[str, Any]]:
    rooms = _rooms_with_beds(request.app.state.db_path, user_id=user["id"])
    return rooms


@router.post("/rooms")
async def create_room(
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Any]:
    _ = body, request, owner
    raise HTTPException(
        status_code=410,
        detail="Nest rooms are owned by the Godot Runtime scene manifest.",
    )


@router.put("/beds/{bed_id}")
async def update_bed(
    bed_id: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Any]:
    _ = bed_id, body, request, owner
    raise HTTPException(
        status_code=410,
        detail="Bed coordinates are owned by the Godot Runtime scene manifest.",
    )


@router.put("/rooms/default/bed-count")
async def update_default_room_bed_count(
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Optional[int]]:
    _ = owner
    bed_count = _bed_count_from_body(body)
    with get_db(request.app.state.db_path) as conn:
        result = SQLiteNestRepository(conn).set_desired_bed_count(bed_count)
        conn.commit()
    desired_bed_count = result["desired_bed_count"]
    if desired_bed_count is None:
        raise HTTPException(status_code=500, detail="bed_count persistence failed")
    return result


@router.put("/rooms/{room_id}/bed-count")
async def update_bed_count(
    room_id: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Optional[int]]:
    if room_id != "local-nest":
        raise HTTPException(status_code=404, detail="Nest not found")
    return await update_default_room_bed_count(body, request, owner)


@router.put("/elfies/{elfie_id}/bed")
async def assign_bed(
    elfie_id: str,
    body: Dict[str, Any],
    request: Request,
    owner: Dict[str, Any] = RequireOwner,
) -> Dict[str, Any]:
    _ = owner
    anchor_id = body.get("home_anchor_id", body.get("bed_id"))
    if anchor_id is not None:
        anchor_id = str(anchor_id)
    try:
        with get_db(request.app.state.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            SQLiteNestRepository(conn).assign_home(
                elfie_id=elfie_id,
                anchor_id=anchor_id,
            )
            conn.commit()
    except NestRepositoryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NestRepositoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"detail": "Home assigned", "home_anchor_id": anchor_id}
