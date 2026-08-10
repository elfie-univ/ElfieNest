"""Session-authenticated, versioned browser and future-client read API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts import AccountPrincipal
from app.features.configuration import food
from app.features.elfie_profile.public_projection import build_public_profile
from app.features.elfies import (
    ElfieNotFound,
    ElfiesUnavailable,
    GetElfieProfileQuery,
    ListVisibleElfiesQuery,
)
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeQueryRepository,
)
from app.interfaces.api.v1.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["v1-client"])


@router.get("/elfies")
async def list_public_elfies(
    request: Request,
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """List the authenticated user's Elfies as public profile projections."""
    return _owned_public_profiles(request, user)


@router.get("/elfies/{elfie_id}/profile")
async def public_elfie_profile(
    elfie_id: str,
    request: Request,
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Read one owned Elfie without exposing raw YAML or local paths."""
    profiles = _owned_public_profiles(request, user)
    for profile in profiles:
        if profile["elfie_id"] == elfie_id:
            return _private_profile_detail(
                request,
                user,
                profile,
            )
    raise HTTPException(status_code=404, detail="精灵不存在")


def _owned_public_profiles(
    request: Request, user: AccountPrincipal
) -> list[Dict[str, Any]]:
    db_path = request.app.state.db_path
    data_home = data_home_from_db_path(db_path)
    records = {
        record.elfie_id: record
        for record in RuntimeQueryRepository(db_path).list_elfies_for_owner(
            user.user_id
        )
    }
    try:
        visible = request.app.state.elfies.list_visible(
            user,
            ListVisibleElfiesQuery(relationship="owned"),
        )
    except ElfiesUnavailable as error:
        raise HTTPException(status_code=503, detail="精灵目录暂不可用") from error
    profiles: list[Dict[str, Any]] = []
    for item in visible:
        projected = item.profile
        record = records.get(projected.elfie_id)
        if record is None:
            continue
        elfie_layout = final_root_layout(data_home).elfie(projected.elfie_id)
        profile = build_public_profile(
            elfie_id=projected.elfie_id,
            name=projected.name,
            species_id=projected.species_id,
            personality_style=projected.summary or "",
            config_dir=str(elfie_layout.profile.parent),
            room_id=None,
            room_name=None,
            bed_id=record.bed_number,
            bed_name=(
                f"Bed {record.bed_number}" if record.bed_number is not None else None
            ),
            embodiment_state=get_embodiment_session(
                db_path, projected.elfie_id
            ).state.value,
        )
        profile["gender"] = projected.gender
        profile["birth_date"] = projected.birth_date
        profile["summary"] = projected.summary
        profile["big_five"] = (
            {} if projected.big_five is None else asdict(projected.big_five)
        )
        profile["personality_tags"] = list(projected.personality_tags)
        profiles.append(profile)
    return profiles


def _private_profile_detail(
    request: Request,
    user: AccountPrincipal,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Add owner-only cognition and read-only care facts to one public profile."""
    elfie_id = str(profile["elfie_id"])
    try:
        detail = request.app.state.elfies.get_profile(
            user,
            GetElfieProfileQuery(elfie_id=elfie_id),
        )
    except ElfieNotFound as error:
        raise HTTPException(status_code=404, detail="精灵不存在") from error
    except ElfiesUnavailable as error:
        raise HTTPException(status_code=503, detail="精灵档案暂不可用") from error
    try:
        policy = request.app.state.food.get_elfie_policy(
            user,
            food.GetMainFoodPolicyQuery(elfie_id=elfie_id),
        )
    except food.FoodNotFound as error:
        raise HTTPException(status_code=404, detail="精灵不存在") from error
    except food.FoodUnavailable as error:
        raise HTTPException(status_code=503, detail="食粮策略暂不可用") from error
    options = [
        {"id": item.food_id, "label": item.display_name}
        for item in policy.main_food_options
    ]
    selected_id = policy.effective_main_food_id or policy.main_food_id
    selected_label = next(
        (item["label"] for item in options if item["id"] == selected_id),
        "",
    )
    return {
        **profile,
        "private_cognition": asdict(detail.private_cognition),
        "care_settings": {
            "food": {
                "selected_id": selected_id,
                "selected_label": selected_label,
                "options": options,
                "unavailable": policy.main_food_unavailable,
            }
        },
    }
