"""Owner-only monitoring projections for every registered Elfie."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.food.elfie_policy import DEFAULT_ALLOWED_FOODS
from ai_runtime.food.models import FIXED_FOOD_KINDS
from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts.auth import require_owner
from app.features.configuration.food_access import elfie_food_policy_projection
from app.features.elfie_profile.public_projection import build_public_profile
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceElfieRecord,
    InterfaceQueryRepository,
)

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
) -> List[InterfaceElfieRecord]:
    return list(
        InterfaceQueryRepository(db_path).list_elfies(
            owner_user_id=owner_user_id,
            species=species_id,
        )
    )


def _filter_monitoring_rows(
    db_path: str,
    rows: List[InterfaceElfieRecord],
    *,
    food_key: Optional[str],
    embodiment_state: Optional[str],
) -> List[Dict[str, Any]]:
    projections = []
    catalog = FoodCatalogStore().load()
    for row in rows:
        state = get_embodiment_session(db_path, row.elfie_id).state.value
        policy = _food_policy(row)
        if food_key is not None and food_key != policy["default_food"]:
            continue
        if embodiment_state is not None and embodiment_state != state:
            continue
        projections.append(_monitoring_projection(db_path, row, state, policy))
    return projections


def _monitoring_projection(
    db_path: str,
    row: InterfaceElfieRecord,
    state: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    data_home = data_home_from_db_path(db_path)
    profile = build_public_profile(
        elfie_id=row.elfie_id,
        name=row.name,
        species_id=row.species,
        personality_style=row.summary or "",
        config_dir=str(final_root_layout(data_home).elfie(row.elfie_id).profile.parent),
        room_id=None,
        room_name=None,
        bed_id=row.bed_number,
        bed_name=None if row.bed_number is None else f"Bed {row.bed_number}",
        embodiment_state=state,
    )
    profile["gender"] = row.gender
    profile["birth_date"] = row.birth_date
    profile["summary"] = row.summary
    return {
        "elfie_id": row.elfie_id,
        "owner": {
            "user_id": row.owner_user_id,
            "username": row.owner_username,
        },
        "profile": profile,
        "food_policy": {
            "main_food_id": policy["main_food_id"],
            "effective_main_food_id": policy["effective_main_food_id"],
            "main_food_options": policy["main_food_options"],
            "main_food_unavailable": policy["main_food_unavailable"],
        },
        "created_at": row.adopted_at,
    }


def _food_policy(row: InterfaceElfieRecord) -> Dict[str, Any]:
    default_food = row.main_food or "standard"
    fallback_food = row.emergency_food or "coarse"
    allowed_set = {default_food, fallback_food, *row.other_foods}
    allowed = [key for key in FIXED_FOOD_KINDS if key in allowed_set]
    return {
        "elfie_id": row.elfie_id,
        "default_food": default_food,
        "allowed_foods": allowed or list(DEFAULT_ALLOWED_FOODS),
        "fallback_food": fallback_food,
    }
