"""普通用户 REST API — 名下精灵列表 + 单精灵配置读写 + 领养端点。

所有端点使用 ``Depends(get_current_user)`` 保护。
精灵所有权校验通过 ``_check_ownership`` 实现（不属于当前用户的返回 404）。
"""

from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .adoption import ElfieGenerator
from .adoption_config import (
    get_allowed_anatomy_types,
    get_allowed_personality_styles,
    get_max_elfies_per_user,
)
from .store import count_elfies_by_owner, get_db

from elfienest.room import RoomFullError

logger = logging.getLogger("elfienest.manage.user_routes")

router = APIRouter(prefix="/api/user", tags=["user"])

# ---------------------------------------------------------------------------
# 有效值常量（与 adoption.py 保持一致）
# ---------------------------------------------------------------------------

PERSONALITY_STYLES: tuple = tuple(ElfieGenerator.PERSONALITY_PRESETS.keys())
HEIGHTS: tuple = ("short", "standard", "tall")
BUILDS: tuple = ("slim", "standard", "plump")

# ---------------------------------------------------------------------------
# 依赖 — 从 session_token cookie 获取当前用户（使用 app.state.db_path）
# ---------------------------------------------------------------------------


def get_current_user(request: Request) -> Dict[str, Any]:
    """FastAPI ``Depends`` 用鉴权中间件。

    从 cookie ``session_token`` 读取 token，调 ``verify_session`` 验证。
    使用 ``request.app.state.db_path`` 作为数据库路径。
    """
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="未登录，缺少会话 token")

    from .auth import verify_session as _verify  # noqa: PLC0415

    db = request.app.state.db_path
    user = _verify(token, db)
    if user is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")
    return user


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
    """返回当前用户名下所有精灵（id, name, anatomy_type, personality_style, height, build, created_at）。"""
    db = request.app.state.db_path
    with get_db(db) as conn:
        cursor = conn.execute(
            """SELECT elfie_id, name, anatomy_type, personality_style,
                      height, build, created_at
               FROM elfie_registry
               WHERE owner_user_id = ?
               ORDER BY created_at DESC""",
            (user["id"],),
        )
        rows = cursor.fetchall()
    return [
        {
            "elfie_id": r["elfie_id"],
            "name": r["name"],
            "anatomy_type": r["anatomy_type"],
            "personality_style": r["personality_style"],
            "height": r["height"],
            "build": r["build"],
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
    """返回单精灵详情 + 当前配置 YAML 内容（personality / capabilities / system_limits）。"""
    db = request.app.state.db_path
    with get_db(db) as conn:
        if not _check_ownership(conn, elfie_id, user["id"]):
            raise HTTPException(status_code=404, detail="精灵不存在")

        cursor = conn.execute(
            """SELECT elfie_id, name, anatomy_type, personality_style,
                      height, build, created_at, config_dir
               FROM elfie_registry WHERE elfie_id = ?""",
            (elfie_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在")

    config_dir = Path(row["config_dir"])
    configs: Dict[str, Any] = {}
    for fname in ("personality.yaml", "capabilities.yaml", "system_limits.yaml"):
        fpath = config_dir / fname
        if fpath.exists():
            configs[fname] = fpath.read_text(encoding="utf-8")
        else:
            configs[fname] = None

    return {
        "elfie_id": row["elfie_id"],
        "name": row["name"],
        "anatomy_type": row["anatomy_type"],
        "personality_style": row["personality_style"],
        "height": row["height"],
        "build": row["build"],
        "created_at": row["created_at"],
        "config_dir": row["config_dir"],
        "configs": configs,
    }


@router.put("/elfies/{elfie_id}/config")
async def update_elfie_config(
    elfie_id: str,
    request: Request,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """更新单精灵配置 YAML 文件。

    请求体: ``{"filename": "personality.yaml", "content": "..."}``
    仅允许更新 ``personality.yaml`` / ``capabilities.yaml`` / ``system_limits.yaml``。
    """
    db = request.app.state.db_path
    with get_db(db) as conn:
        if not _check_ownership(conn, elfie_id, user["id"]):
            raise HTTPException(status_code=404, detail="精灵不存在")

        cursor = conn.execute(
            "SELECT config_dir FROM elfie_registry WHERE elfie_id = ?",
            (elfie_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="精灵不存在")

    config_dir = Path(row["config_dir"])
    filename = (body.get("filename") or "").strip()
    content = body.get("content")

    if filename not in (
        "personality.yaml",
        "capabilities.yaml",
        "system_limits.yaml",
    ):
        raise HTTPException(
            status_code=400,
            detail="filename 必须是 personality.yaml / capabilities.yaml / system_limits.yaml 之一",
        )
    if not content or not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content 不能为空且必须为字符串")

    fpath = config_dir / filename
    fpath.write_text(content, encoding="utf-8")
    logger.info(
        "User %s updated %s for elfie %s", user["username"], filename, elfie_id,
    )
    return {"detail": f"{filename} 已更新"}


@router.post("/adopt")
async def adopt_elfie(
    request: Request,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """核心领养端点 — 创建新精灵并分配至当前用户。

    前置检查：上限 3 只、名字长度、anatomy_type、personality_style、height、build。
    通过后：生成 elfie_id → 调用 ElfieGenerator → 插入 elfie_registry → 可选注册到 engine。
    """
    name = (body.get("name") or "").strip()
    anatomy_type = (body.get("anatomy_type") or "").strip()
    personality_style = (body.get("personality_style") or "").strip()
    height = (body.get("height") or "").strip()
    build = (body.get("build") or "").strip()

    # ------------------------------------------------------------------
    # 前置检查
    # ------------------------------------------------------------------
    if not name or len(name) > 20:
        raise HTTPException(
            status_code=400,
            detail="名字长度必须在 1-20 字之间",
        )
    db = request.app.state.db_path

    allowed_anatomy = get_allowed_anatomy_types(db)
    if anatomy_type not in allowed_anatomy:
        raise HTTPException(
            status_code=400,
            detail=f"anatomy_type 必须是 {allowed_anatomy}",
        )

    allowed_styles = get_allowed_personality_styles(db)
    if personality_style not in allowed_styles:
        raise HTTPException(
            status_code=400,
            detail=f"personality_style 必须是 {list(allowed_styles)}",
        )
    if height not in HEIGHTS:
        raise HTTPException(
            status_code=400,
            detail=f"height 必须是 {HEIGHTS}",
        )
    if build not in BUILDS:
        raise HTTPException(
            status_code=400,
            detail=f"build 必须是 {BUILDS}",
        )

    # 领养上限检查
    max_per_user = get_max_elfies_per_user(db)
    current_count = count_elfies_by_owner(user["id"], db)
    if current_count >= max_per_user:
        raise HTTPException(
            status_code=409,
            detail=f"每用户最多领养 {max_per_user} 只精灵",
        )

    # ------------------------------------------------------------------
    # 生成 elfie_id & config_dir
    # ------------------------------------------------------------------
    elfie_id = f"elfie_{int(time.time())}_{secrets.token_hex(2)}"
    config_dir = f"data/elfies/{elfie_id}"

    # 调用 ElfieGenerator 生成 3 个 YAML 配置文件
    try:
        ElfieGenerator().generate(
            name=name,
            anatomy_type=anatomy_type,
            personality_style=personality_style,
            height=height,
            build=build,
            config_dir=config_dir,
            elfie_id=elfie_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    # 插入 elfie_registry 表
    with get_db(db) as conn:
        conn.execute(
            """INSERT INTO elfie_registry
               (elfie_id, name, owner_user_id, anatomy_type, config_dir,
                personality_style, height, build)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                elfie_id,
                name,
                user["id"],
                anatomy_type,
                config_dir,
                personality_style,
                height,
                build,
            ),
        )
        conn.commit()

    # 如果 engine 实例存在，尝试实例化 ElfieIndividual 并注册到房间
    engine = getattr(request.app.state, "engine", None)
    if engine is not None:
        try:
            from elfie.elfie_individual import ElfieIndividual  # noqa: PLC0415

            elfie = ElfieIndividual(config_dir=config_dir, anatomy_type=anatomy_type)
            engine.coordinator.register_elfie(elfie_id, elfie)
            logger.info(
                "Elfie %s (%s) registered to room via engine", elfie_id, name,
            )
        except RoomFullError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except Exception as exc:
            logger.warning(
                "Failed to register elfie %s to engine: %s", elfie_id, exc,
            )

    return JSONResponse(
        status_code=201,
        content={
            "elfie_id": elfie_id,
            "name": name,
            "config_dir": config_dir,
        },
    )


@router.get("/adoption-info")
async def adoption_info(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
):
    """返回领养可选项（性格风格列表、体型列表、身高/体型选项）。

    性格风格和 anatomy_type 从 ``system.adoption`` 动态读取。
    """
    db = request.app.state.db_path
    return {
        "personality_styles": list(get_allowed_personality_styles(db)),
        "anatomy_types": list(get_allowed_anatomy_types(db)),
        "heights": list(HEIGHTS),
        "builds": list(BUILDS),
    }
