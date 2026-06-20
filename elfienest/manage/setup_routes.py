"""首启向导端点 — setup-status + setup"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import create_session, generate_csrf_token
from .store import get_db, hash_password

logger = logging.getLogger("elfienest.manage.setup_routes")

router = APIRouter(prefix="/api/auth", tags=["setup"])


class SetupStatus(BaseModel):
    need_setup: bool


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    avatar_color: Optional[int] = Field(None, ge=0, le=7)


@router.get("/setup-status")
async def get_setup_status(request: Request) -> SetupStatus:
    """检查是否需要首启设置（没有用户时返回 need_setup=true）"""
    db_path = request.app.state.db_path
    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
    return SetupStatus(need_setup=(count == 0))


@router.post("/setup", status_code=201)
async def do_setup(body: SetupRequest, request: Request) -> JSONResponse:
    """首启设置 — 创建第一个管理员账号。仅在无用户时允许。"""
    db_path = request.app.state.db_path

    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0:
            raise HTTPException(status_code=409, detail="系统已有用户，无法执行首启设置")

        pw_hash = hash_password(body.password)
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role, nickname, avatar_color, avatar_kind) VALUES (?, ?, 'admin', ?, ?, 'initials')",
            (body.username, pw_hash, body.username, body.avatar_color or 0),
        )
        user_id = cursor.lastrowid
        conn.commit()

        session_token = create_session(user_id, db_path)

    csrf_token = generate_csrf_token(session_token)
    response = JSONResponse(
        content={
            "id": user_id,
            "username": body.username,
            "role": "admin",
            "csrf_token": csrf_token,
        },
        status_code=201,
    )
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    response.headers["X-CSRF-Token"] = csrf_token
    return response
