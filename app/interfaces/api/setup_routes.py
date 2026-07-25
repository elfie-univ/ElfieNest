"""首启向导端点 — setup-status + setup"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.features.accounts.auth import get_session_ttl_seconds
from app.features.setup.service import (
    SetupAlreadyCompleteError,
    create_first_owner,
    needs_setup,
)

_LOCAL_SETUP_CLIENTS = frozenset({"127.0.0.1", "::1", "testclient"})

logger = logging.getLogger("app.interfaces.api.setup_routes")

router = APIRouter(prefix="/api/auth", tags=["setup"])


class SetupStatus(BaseModel):
    need_setup: bool


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    avatar_color: Optional[int] = Field(None, ge=0, le=7)


def _require_local_setup_client(request: Request) -> None:
    """首次 Owner 只能由本机/Electron 回环请求创建。"""
    client_host = request.client.host if request.client is not None else ""
    if client_host not in _LOCAL_SETUP_CLIENTS:
        raise HTTPException(status_code=403, detail="首次设置仅允许在本机完成")


@router.get("/setup-status")
async def get_setup_status(request: Request) -> SetupStatus:
    """检查是否需要首启设置（没有用户时返回 need_setup=true）"""
    return SetupStatus(need_setup=needs_setup(request.app.state.db_path))


@router.post("/setup", status_code=201)
async def do_setup(body: SetupRequest, request: Request) -> JSONResponse:
    """首启设置 — 创建第一个 Owner 账号。仅在无用户时允许。"""
    _require_local_setup_client(request)
    db_path = request.app.state.db_path
    try:
        setup_result = create_first_owner(
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
        max_age=get_session_ttl_seconds(db_path),
    )
    response.headers["X-CSRF-Token"] = setup_result.csrf_token
    return response
