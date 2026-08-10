"""Manager monitoring projections for every registered Elfie."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts import AccountPrincipal
from app.features.configuration import food
from app.features.elfie_profile.public_projection import build_public_profile
from app.features.elfies import (
    AdminElfieResult,
    ElfiesUnavailable,
    ListAdminElfiesQuery,
)
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceElfieRecord,
    InterfaceQueryRepository,
)
from app.interfaces.api.v1.auth import require_manager
from app.orchestration.embodiment import EmbodimentSessionService

router = APIRouter(prefix="/api/owner", tags=["owner-elfie-monitoring"])


@router.get("/elfies")
async def list_owner_elfie_monitoring(
    request: Request,
    owner_user_id: Optional[str] = None,
    species_id: Optional[str] = None,
    food_key: Optional[str] = None,
    embodiment_state: Optional[str] = None,
    status: Optional[str] = None,
    owner: AccountPrincipal = Depends(require_manager),  # noqa: B008
) -> List[Dict[str, Any]]:
    """List safe operational summaries without private configuration or chats."""
    owner_id = _optional_owner_id(owner_user_id)
    species = _optional_text(species_id)
    try:
        projections = request.app.state.elfies.list_admin(
            owner,
            ListAdminElfiesQuery(owner_user_id=owner_id, species_id=species),
        )
    except ElfiesUnavailable as error:
        raise HTTPException(status_code=503, detail="精灵目录暂不可用") from error
    rows = _load_registered_elfies(
        request.app.state.db_path,
        owner_id,
        species,
    )
    return _filter_monitoring_rows(
        request.app.state.db_path,
        request.app.state.embodiment,
        rows,
        {item.profile.elfie_id: item for item in projections},
        owner,
        request.app.state.food,
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
    embodiment: EmbodimentSessionService,
    rows: List[InterfaceElfieRecord],
    elfies: Dict[str, AdminElfieResult],
    principal: AccountPrincipal,
    food_service: food.FoodService,
    *,
    food_key: Optional[str],
    embodiment_state: Optional[str],
) -> List[Dict[str, Any]]:
    projections = []
    for row in rows:
        elfie = elfies.get(row.elfie_id)
        if elfie is None:
            continue
        state = embodiment.get_session(row.elfie_id).state.value
        try:
            policy = food_service.get_elfie_policy(
                principal,
                food.GetMainFoodPolicyQuery(elfie_id=row.elfie_id),
            )
        except food.FoodNotFound:
            continue
        except food.FoodUnavailable as error:
            raise HTTPException(status_code=503, detail="食粮策略暂不可用") from error
        if food_key is not None and food_key != policy.effective_main_food_id:
            continue
        if embodiment_state is not None and embodiment_state != state:
            continue
        projections.append(_monitoring_projection(db_path, row, elfie, state, policy))
    return projections


def _monitoring_projection(
    db_path: str,
    row: InterfaceElfieRecord,
    elfie: AdminElfieResult,
    state: str,
    policy: food.MainFoodPolicyResult,
) -> Dict[str, Any]:
    data_home = data_home_from_db_path(db_path)
    source = elfie.profile
    profile = build_public_profile(
        elfie_id=source.elfie_id,
        name=source.name,
        species_id=source.species_id,
        personality_style=source.summary or "",
        config_dir=str(
            final_root_layout(data_home).elfie(source.elfie_id).profile.parent
        ),
        room_id=None,
        room_name=None,
        bed_id=row.bed_number,
        bed_name=None if row.bed_number is None else f"Bed {row.bed_number}",
        embodiment_state=state,
    )
    profile["gender"] = source.gender
    profile["birth_date"] = source.birth_date
    profile["summary"] = source.summary
    profile["big_five"] = {} if source.big_five is None else asdict(source.big_five)
    profile["personality_tags"] = list(source.personality_tags)
    return {
        "elfie_id": source.elfie_id,
        "owner": {
            "user_id": elfie.owner.user_id,
            "account_id": elfie.owner.account_id,
            "display_name": elfie.owner.display_name,
        },
        "profile": profile,
        "food_policy": {
            "main_food_id": policy.main_food_id,
            "effective_main_food_id": policy.effective_main_food_id,
            "main_food_options": [
                {"food_id": item.food_id, "display_name": item.display_name}
                for item in policy.main_food_options
            ],
            "main_food_unavailable": policy.main_food_unavailable,
        },
        "created_at": source.adopted_at,
    }
