"""首启向导端点 — setup-status + setup"""

from __future__ import annotations

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ai_runtime.models.local_profiles import recommend_local_profile
from app.features.accounts.auth import get_session_ttl_seconds, require_owner
from app.features.setup.hardware import get_available_memory_gb
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.progress import SetupTask, get_setup_task
from app.features.setup.service import (
    SetupAlreadyCompleteError,
    complete_setup_step,
    create_first_owner,
    get_setup_progress,
)
from app.infrastructure.ollama_platform import OllamaPlatformAdapter
from app.infrastructure.persistence.nest_repository import SQLiteNestRepository
from app.infrastructure.persistence.store import get_db

_LOCAL_SETUP_CLIENTS = frozenset({"127.0.0.1", "::1", "testclient"})

logger = logging.getLogger("app.interfaces.api.setup_routes")

router = APIRouter(prefix="/api/auth", tags=["setup"])
RequireOwner = Depends(require_owner)


class SetupStepStatus(BaseModel):
    number: int
    name: str
    status: str
    retry_action: Optional[str] = None


class SetupTaskStatus(BaseModel):
    step: int
    key: str
    state: str
    progress: int
    error: Optional[str] = None


class SetupStatus(BaseModel):
    need_setup: bool
    complete: bool
    current_step: int
    steps: List[SetupStepStatus]
    last_error: Optional[str] = None
    task: Optional[SetupTaskStatus] = None


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    display_name: Optional[str] = Field(None, min_length=1, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    avatar_color: Optional[int] = Field(None, ge=0, le=7)


class SetupOllamaRequest(BaseModel):
    decision: Literal["bound_existing", "skipped"]
    endpoint: Optional[str] = Field(None, min_length=1, max_length=256)


class SetupOllamaInstallRequest(BaseModel):
    confirmed: Literal[True]


class SetupNestRequest(BaseModel):
    bed_count: int = Field(..., ge=4, le=32)


class SetupModelRequest(BaseModel):
    decision: Literal["configured", "skipped"]
    model_reference: Optional[str] = Field(None, min_length=3, max_length=256)


class SetupModelRecommendation(BaseModel):
    memory_gb: int
    recommended_model: Optional[str] = None


class SetupModelPullRequest(BaseModel):
    model_reference: str = Field(..., min_length=3, max_length=256)
    confirmed: Literal[True]


def _require_local_setup_client(request: Request) -> None:
    """首次 Owner 只能由本机/Electron 回环请求创建。"""
    client_host = request.client.host if request.client is not None else ""
    if client_host not in _LOCAL_SETUP_CLIENTS:
        raise HTTPException(status_code=403, detail="首次设置仅允许在本机完成")


@router.get("/setup-status")
async def get_setup_status(request: Request) -> SetupStatus:
    """返回可恢复的五步首启状态，不能用 Owner 是否存在代替完成状态。"""
    return _setup_status(request)


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
            display_name=body.display_name,
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


@router.post("/setup/ollama")
async def complete_setup_ollama(
    body: SetupOllamaRequest,
    request: Request,
    owner: dict = RequireOwner,
) -> SetupStatus:
    """Record the explicit offline-capability choice; installation jobs are separate."""
    _ = owner
    if body.decision == "skipped":
        complete_setup_step(request.app.state.db_path, step=2, decision=body.decision)
    else:
        if not body.endpoint:
            raise HTTPException(status_code=422, detail="绑定已有 Ollama 需要 endpoint")
        service = OllamaSetupService(
            adapter=OllamaPlatformAdapter(),
        )
        try:
            service.bind_existing(
                db_path=request.app.state.db_path,
                endpoint=body.endpoint.strip(),
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _setup_status(request)


@router.post("/setup/ollama/install", status_code=202)
async def install_setup_ollama(
    body: SetupOllamaInstallRequest,
    request: Request,
    owner: dict = RequireOwner,
) -> SetupStatus:
    """Queue one explicitly confirmed official installer; the request never runs it."""
    _ = body
    _ = owner

    def install() -> None:
        service = OllamaSetupService(
            adapter=OllamaPlatformAdapter(),
        )
        service.install_official(
            db_path=request.app.state.db_path,
            endpoint="http://127.0.0.1:11434",
            user_confirmed=True,
        )

    try:
        task = request.app.state.setup_ollama_jobs.start(
            db_path=request.app.state.db_path,
            worker=install,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    status = _setup_status(request)
    status.task = _task_status(task)
    return status


@router.put("/setup/nest")
async def complete_setup_nest(
    body: SetupNestRequest,
    request: Request,
    owner: dict = RequireOwner,
) -> SetupStatus:
    _ = owner
    with get_db(request.app.state.db_path) as conn:
        SQLiteNestRepository(conn).set_desired_bed_count(body.bed_count)
        conn.commit()
    complete_setup_step(request.app.state.db_path, step=3)
    return _setup_status(request)


@router.get("/setup/model-recommendation")
async def get_setup_model_recommendation(
    owner: dict = RequireOwner,
) -> SetupModelRecommendation:
    """Recommend a local model only when the host clears the 4 GiB floor."""
    _ = owner
    memory_gb = get_available_memory_gb()
    profile = recommend_local_profile(memory_gb)
    return SetupModelRecommendation(
        memory_gb=memory_gb,
        recommended_model=(f"ollama/{profile.text_model}" if profile else None),
    )


@router.post("/setup/model")
async def complete_setup_model(
    body: SetupModelRequest,
    request: Request,
    owner: dict = RequireOwner,
) -> SetupStatus:
    _ = owner
    if body.decision == "skipped":
        complete_setup_step(request.app.state.db_path, step=4, decision=body.decision)
        return _setup_status(request)
    if not body.model_reference:
        raise HTTPException(
            status_code=422, detail="配置模型需要完整 provider_id/model_id"
        )
    service = OllamaSetupService(
        adapter=OllamaPlatformAdapter(),
    )
    try:
        service.configure_installed_model(
            db_path=request.app.state.db_path,
            model_reference=body.model_reference,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _setup_status(request)


@router.post("/setup/model/pull", status_code=202)
async def pull_setup_model(
    body: SetupModelPullRequest,
    request: Request,
    owner: dict = RequireOwner,
) -> SetupStatus:
    """Queue an explicitly confirmed model pull against the fixed Ollama endpoint."""
    _ = body.confirmed
    _ = owner

    def pull() -> None:
        service = OllamaSetupService(
            adapter=OllamaPlatformAdapter(),
        )
        service.pull_and_configure_model(
            db_path=request.app.state.db_path,
            model_reference=body.model_reference,
        )

    try:
        task = request.app.state.setup_ollama_jobs.start_model_pull(
            db_path=request.app.state.db_path,
            worker=pull,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    status = _setup_status(request)
    status.task = _task_status(task)
    return status


@router.post("/setup/complete")
async def complete_setup_confirmation(
    request: Request,
    owner: dict = RequireOwner,
) -> SetupStatus:
    _ = owner
    complete_setup_step(request.app.state.db_path, step=5)
    return _setup_status(request)


def _setup_status(request: Request) -> SetupStatus:
    progress = get_setup_progress(request.app.state.db_path)
    task = get_setup_task(request.app.state.db_path)
    return SetupStatus(
        need_setup=not progress.complete,
        complete=progress.complete,
        current_step=progress.current_step,
        steps=[SetupStepStatus(**step.__dict__) for step in progress.steps],
        last_error=progress.last_error,
        task=_task_status(task),
    )


def _task_status(task: SetupTask | None) -> SetupTaskStatus | None:
    if task is None:
        return None
    return SetupTaskStatus(
        step=task.step,
        key=task.key,
        state=task.state,
        progress=task.progress,
        error=task.error,
    )
