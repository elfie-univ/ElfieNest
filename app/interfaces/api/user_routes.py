"""普通用户 REST API — 名下精灵列表、公开详情与领养端点。

所有端点使用 ``Depends(get_current_user)`` 保护。
精灵所有权校验通过 ``_check_ownership`` 实现（不属于当前用户的返回 404）。
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

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
from app.infrastructure.persistence.store import get_db
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


def _check_ownership(conn, elfie_id: str, user_id: int) -> bool:
    """检查 *elfie_id* 的 owner_user_id 是否等于 *user_id*。"""
    cur = conn.execute(
        "SELECT owner_user_id FROM elfie_registry WHERE elfie_id=?",
        (elfie_id,),
    )
    row = cur.fetchone()
    return row is not None and row[0] == user_id


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
    with get_db(db) as conn:
        cursor = conn.execute(
            """SELECT e.elfie_id,
                      e.name,
                      e.species_id,
                      e.personality_style,
                      e.height,
                      e.build,
                      e.bed_id,
                      b.name AS bed_name,
                      r.id AS room_id,
                      r.name AS room_name,
                      e.created_at
               FROM elfie_registry e
               LEFT JOIN beds b ON b.id = e.bed_id
               LEFT JOIN rooms r ON r.id = b.room_id
               WHERE e.owner_user_id = ?
               ORDER BY e.created_at DESC""",
            (user["id"],),
        )
        rows = cursor.fetchall()
    return [
        {
            "elfie_id": r["elfie_id"],
            "name": r["name"],
            "species_id": r["species_id"],
            "personality_style": r["personality_style"],
            "height": r["height"],
            "build": r["build"],
            "bed_id": r["bed_id"],
            "bed_name": r["bed_name"],
            "room_id": r["room_id"],
            "room_name": r["room_name"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.get("/elfies/{elfie_id}")
async def get_elfie_detail(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """返回当前用户自己精灵的安全公开资料，不暴露原始配置。"""
    db = request.app.state.db_path
    with get_db(db) as conn:
        if not _check_ownership(conn, elfie_id, user["id"]):
            raise HTTPException(status_code=404, detail="精灵不存在")

        cursor = conn.execute(
            """SELECT e.elfie_id, e.name, e.species_id, e.personality_style,
                      e.config_dir, e.bed_id, b.name AS bed_name,
                      r.id AS room_id, r.name AS room_name
               FROM elfie_registry e
               LEFT JOIN beds b ON b.id = e.bed_id
               LEFT JOIN rooms r ON r.id = b.room_id
               WHERE e.elfie_id = ?""",
            (elfie_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在")

    return build_public_profile(
        elfie_id=str(row["elfie_id"]),
        name=str(row["name"]),
        species_id=str(row["species_id"]),
        personality_style=str(row["personality_style"] or ""),
        config_dir=str(row["config_dir"]) if row["config_dir"] else None,
        room_id=int(row["room_id"]) if row["room_id"] is not None else None,
        room_name=str(row["room_name"]) if row["room_name"] is not None else None,
        bed_id=int(row["bed_id"]) if row["bed_id"] is not None else None,
        bed_name=str(row["bed_name"]) if row["bed_name"] is not None else None,
        embodiment_state=get_embodiment_session(db, elfie_id).state.value,
    )


@router.post("/adopt")
async def adopt_elfie(
    request: Request,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """核心领养端点 — 创建新精灵并分配至当前用户。

    前置检查：领养上限、名字、物种、性格方向和外貌生成方向。
    通过后：生成 elfie_id → 调用 ElfieGenerator → 插入 elfie_registry → 可选注册到 engine。
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
