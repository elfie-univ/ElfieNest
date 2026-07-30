"""普通用户 REST API — 名下精灵列表、公开详情与领养端点。

所有端点使用 ``Depends(get_current_user)`` 保护。
精灵所有权校验通过 ``_check_ownership`` 实现（不属于当前用户的返回 404）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts.auth import get_current_user
from app.features.adoption.generator import ElfieGenerator
from app.features.adoption.service import (
    AdoptionCapacityError,
    AdoptionRequest,
    AdoptionValidationError,
    adopt_elfie_for_user,
    adoption_options_for_user,
)
from app.features.elfie_profile.public_projection import build_public_profile
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceElfieRecord,
    InterfaceQueryRepository,
)
from app.interfaces.api.user_chat_routes import router as user_chat_router
from nest import NestFullError

router = APIRouter(prefix="/api/user", tags=["user"])
router.include_router(user_chat_router)

# ---------------------------------------------------------------------------
# 有效值常量（与 adoption.py 保持一致）
# ---------------------------------------------------------------------------

PERSONALITY_STYLES: tuple = tuple(ElfieGenerator.PERSONALITY_PRESETS.keys())
HEIGHTS: tuple = ("short", "standard", "tall")
BUILDS: tuple = ("slim", "standard", "plump")

# ---------------------------------------------------------------------------
# 助手 — 校验精灵所有权
# ---------------------------------------------------------------------------


def _profile_dir(db_path: str, elfie_id: str) -> str:
    data_home = Path(db_path).expanduser().resolve().parent
    return str(final_root_layout(data_home).elfie(elfie_id).profile.parent)


def _public_profile(db_path: str, record: InterfaceElfieRecord) -> Dict[str, object]:
    profile = build_public_profile(
        elfie_id=record.elfie_id,
        name=record.name,
        species_id=record.species,
        personality_style=record.summary or "",
        config_dir=_profile_dir(db_path, record.elfie_id),
        room_id=None,
        room_name=None,
        bed_id=record.bed_number,
        bed_name=(None if record.bed_number is None else f"Bed {record.bed_number}"),
        embodiment_state=get_embodiment_session(db_path, record.elfie_id).state.value,
    )
    profile["gender"] = record.gender
    profile["birth_date"] = record.birth_date
    profile["summary"] = record.summary
    return profile


# ===================================================================
# 端点
# ===================================================================


@router.get("/elfies")
async def list_my_elfies(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """返回当前用户名下所有精灵及其稳定物种和领养摘要。"""
    db = request.app.state.db_path
    rows = InterfaceQueryRepository(db).list_elfies(owner_user_id=int(user["id"]))
    return [
        {
            "elfie_id": row.elfie_id,
            "name": row.name,
            "species_id": row.species,
            "personality_style": row.summary,
            "height": None,
            "build": None,
            "bed_id": row.bed_number,
            "bed_name": (None if row.bed_number is None else f"Bed {row.bed_number}"),
            "room_id": None,
            "room_name": None,
            "created_at": row.adopted_at,
        }
        for row in rows
    ]


@router.get("/elfies/{elfie_id}")
async def get_elfie_detail(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """返回当前用户自己精灵的安全公开资料，不暴露原始配置。"""
    db = request.app.state.db_path
    record = InterfaceQueryRepository(db).get_elfie(
        elfie_id, owner_user_id=int(user["id"])
    )
    if record is None:
        raise HTTPException(status_code=404, detail="精灵不存在")
    return _public_profile(db, record)


@router.post("/adopt")
async def adopt_elfie(
    request: Request,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """核心领养端点 — 创建新精灵并分配至当前用户。

    前置检查：领养上限、名字、物种、性格方向和外貌生成方向。
    通过后：生成 elfie_id → 调用 ElfieGenerator → 写入最终 Elfie 存储 → 可选注册到 engine。
    """
    db = request.app.state.db_path
    adoption_request = AdoptionRequest(
        name=(body.get("name") or "").strip(),
        species_id=(
            body.get("species_id") or ("fox" if body.get("anatomy_type") else "")
        ).strip(),
        personality_style=(body.get("personality_style") or "").strip(),
        height=(body.get("height") or "").strip(),
        build=(body.get("build") or "").strip(),
        appearance_overrides=body.get("appearance_overrides", {}),
    )
    engine = getattr(request.app.state, "engine", None)
    try:
        result = adopt_elfie_for_user(
            db,
            user_id=user["id"],
            request=adoption_request,
            engine=engine,
        )
    except AdoptionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except (AdoptionCapacityError, NestFullError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    return JSONResponse(
        status_code=201,
        content={
            "elfie_id": result.elfie_id,
            "name": result.name,
            "species_id": result.species_id,
        },
    )


@router.get("/adoption-info")
async def adoption_info(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """返回领养可选项（物种、性格以及外貌生成方向）。

    性格风格和 species_id 从 ``system.adoption`` 动态读取。
    """
    return adoption_options_for_user(request.app.state.db_path, user_id=user["id"])
