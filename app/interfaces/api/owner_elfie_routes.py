"""Owner-only monitoring projections for every registered Elfie."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.food.elfie_policy import load_elfie_food_policy
from app.features.accounts.auth import require_owner
from app.features.elfie_profile.public_projection import build_public_profile
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.store import get_db

router = APIRouter(prefix="/api/owner", tags=["owner-elfie-monitoring"])


@router.get("/elfies")
async def list_owner_elfie_monitoring(
    request: Request,
    owner_user_id: Optional[str] = None,
    species_id: Optional[str] = None,
    food_key: Optional[str] = None,
    embodiment_state: Optional[str] = None,
    status: Optional[str] = None,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> List[Dict[str, Any]]:
    """List safe operational summaries without private configuration or chats."""
    _ = owner
    rows = _load_registered_elfies(
        request.app.state.db_path,
        _optional_owner_id(owner_user_id),
        _optional_text(species_id),
    )
    return _filter_monitoring_rows(
        request.app.state.db_path,
        rows,
        food_key=_optional_text(food_key),
        embodiment_state=_optional_text(embodiment_state) or _optional_text(status),
    )


def _optional_text(value: Optional[str]) -> Optional[str]:
    normalized = (value or "").strip()
    return normalized or None


def _optional_owner_id(value: Optional[str]) -> Optional[int]:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="owner_user_id 必须是整数") from exc


def _load_registered_elfies(
    db_path: str,
    owner_user_id: Optional[int],
    species_id: Optional[str],
) -> List[Dict[str, Any]]:
    clauses = []
    parameters: List[Any] = []
    if owner_user_id is not None:
        clauses.append("e.owner_user_id = ?")
        parameters.append(owner_user_id)
    if species_id is not None:
        clauses.append("e.species_id = ?")
        parameters.append(species_id)
    where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = (
        """
        SELECT e.elfie_id, e.name, e.owner_user_id, u.username AS owner_username,
               e.species_id, e.personality_style, e.height, e.build, e.config_dir,
               e.bed_id, b.name AS bed_name, r.id AS room_id, r.name AS room_name,
               e.created_at
        FROM elfie_registry e
        LEFT JOIN users u ON u.id = e.owner_user_id
        LEFT JOIN beds b ON b.id = e.bed_id
        LEFT JOIN rooms r ON r.id = b.room_id
    """
        + where_clause
        + " ORDER BY e.created_at DESC"
    )
    with get_db(db_path) as connection:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def _filter_monitoring_rows(
    db_path: str,
    rows: List[Dict[str, Any]],
    *,
    food_key: Optional[str],
    embodiment_state: Optional[str],
) -> List[Dict[str, Any]]:
    projections = []
    for row in rows:
        state = get_embodiment_session(db_path, str(row["elfie_id"])).state.value
        policy = load_elfie_food_policy(str(row["elfie_id"]), str(row["config_dir"]))
        if food_key is not None and food_key != policy.default_food:
            continue
        if embodiment_state is not None and embodiment_state != state:
            continue
        projections.append(_monitoring_projection(row, state, policy.to_dict()))
    return projections


def _monitoring_projection(
    row: Dict[str, Any], state: str, policy: Dict[str, Any]
) -> Dict[str, Any]:
    profile = build_public_profile(
        elfie_id=str(row["elfie_id"]),
        name=str(row["name"]),
        species_id=str(row["species_id"]),
        personality_style=str(row["personality_style"] or ""),
        config_dir=str(row["config_dir"]) if row["config_dir"] else None,
        room_id=int(row["room_id"]) if row["room_id"] is not None else None,
        room_name=str(row["room_name"]) if row["room_name"] is not None else None,
        bed_id=int(row["bed_id"]) if row["bed_id"] is not None else None,
        bed_name=str(row["bed_name"]) if row["bed_name"] is not None else None,
        embodiment_state=state,
    )
    return {
        "elfie_id": str(row["elfie_id"]),
        "owner": {
            "user_id": int(row["owner_user_id"]),
            "username": str(row["owner_username"] or ""),
        },
        "profile": profile,
        "food_policy": {
            "default_food": policy["default_food"],
            "allowed_foods": policy["allowed_foods"],
            "fallback_food": policy["fallback_food"],
        },
        "created_at": str(row["created_at"]),
    }
