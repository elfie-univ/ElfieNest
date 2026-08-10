from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.infrastructure.persistence.nest_repository import (
    NestRepositoryConflictError,
    NestRepositoryNotFoundError,
    RoomPayload,
    SQLiteNestRepository,
)
from app.infrastructure.persistence.store import get_db
from app.interfaces.api.v1.auth import require_manager

router = APIRouter(prefix="/api/owner/nest", tags=["nest"])
RequireOwner = Depends(require_manager)
DEFAULT_BED_COUNT = 4
MIN_BED_COUNT = 4
MAX_BED_COUNT = 32


def _rooms_with_beds(
    db_path: str,
) -> List[RoomPayload]:
    with get_db(db_path) as conn:
        repository = SQLiteNestRepository(conn)
        rooms = repository.load_view().as_rooms_payload()
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
    return cast(List[Dict[str, Any]], rooms)


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
            SQLiteNestRepository(conn).assign_home_immediately(
                elfie_id=elfie_id,
                anchor_id=anchor_id,
            )
            conn.commit()
    except NestRepositoryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NestRepositoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"detail": "Home assigned", "home_anchor_id": anchor_id}
