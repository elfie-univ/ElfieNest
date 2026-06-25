"""首启向导端点 — setup-status + setup"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from elfienest.setup.service import (
    SetupAlreadyCompleteError,
    create_first_admin,
    needs_setup,
)

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
    return SetupStatus(need_setup=needs_setup(request.app.state.db_path))


@router.post("/setup", status_code=201)
async def do_setup(body: SetupRequest, request: Request) -> JSONResponse:
    """首启设置 — 创建第一个管理员账号。仅在无用户时允许。"""
    db_path = request.app.state.db_path
    try:
        setup_result = create_first_admin(
            db_path,
            username=body.username,
            password=body.password,
            avatar_color=body.avatar_color or 0,
        )
    except SetupAlreadyCompleteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    response = JSONResponse(
        content={
            "id": setup_result.user_id,
            "username": setup_result.username,
            "role": setup_result.role,
            "csrf_token": setup_result.csrf_token,
        },
        status_code=201,
    )
    response.set_cookie(
        key="session_token",
        value=setup_result.session_token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    response.headers["X-CSRF-Token"] = setup_result.csrf_token
    return response
