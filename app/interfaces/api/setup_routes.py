"""首启向导端点 — draft 状态与统一安装任务。"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ai_runtime.models.local_profiles import recommend_local_profile
from app.features.accounts.auth import (
    create_session,
    generate_csrf_token,
    get_session_ttl_seconds,
    hash_password,
    require_owner,
    verify_session,
)
from app.features.setup.hardware import get_available_memory_gb
from app.features.setup.installer import build_setup_install_worker
from app.features.setup.model_catalog import setup_model_options
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.service import (
    SetupAlreadyCompleteError,
    create_first_owner_from_hash,
    has_owner,
    save_offline_setup_draft,
)
from app.infrastructure.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaPlatformAdapter,
)
from app.infrastructure.ollama_platform_commands import official_launch_target
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)

from .setup_models import (
    SetupDraftView,
    SetupInstallRequest,
    SetupInstallStatus,
    SetupModelOptionResponse,
    SetupModelRecommendation,
    SetupNestDraftRequest,
    SetupOfflineDraftRequest,
    SetupOllamaDetection,
    SetupOwnerDraftRequest,
    SetupStatus,
    SetupStepStatus,
)

_LOCAL_SETUP_CLIENTS = frozenset({"127.0.0.1", "::1", "testclient"})

router = APIRouter(prefix="/api/auth", tags=["setup"])
RequireOwner = Depends(require_owner)


def _require_local_setup_client(request: Request) -> None:
    """首次 Owner 只能由本机/Electron 回环请求创建。"""
    client_host = request.client.host if request.client is not None else ""
    if client_host not in _LOCAL_SETUP_CLIENTS:
        raise HTTPException(status_code=403, detail="首次设置仅允许在本机完成")


@router.get("/setup-status")
async def get_setup_status(request: Request) -> SetupStatus:
    """Return recoverable Setup state and issue a temporary local token before Owner."""
    status = _setup_status(request)
    if status.need_setup and not _has_owner(request):
        token = request.cookies.get("setup_token") or secrets.token_hex(32)
        status = status.model_copy(update={"csrf_token": generate_csrf_token(token)})
        response = JSONResponse(content=status.model_dump(mode="json"))
        response.set_cookie(
            key="setup_token",
            value=token,
            httponly=True,
            samesite="strict",
            max_age=900,
            path="/",
        )
        response.headers["X-CSRF-Token"] = generate_csrf_token(token)
        return response
    return status


@router.get("/setup/model-catalog")
async def get_setup_model_catalog() -> list[SetupModelOptionResponse]:
    return [
        SetupModelOptionResponse(
            model_id=option.model_id,
            label=option.label,
            approx_download_mb=option.approx_download_mb,
            recommended=option.recommended,
        )
        for option in setup_model_options()
    ]


@router.put("/setup/draft/owner")
async def save_setup_owner_draft(
    body: SetupOwnerDraftRequest,
    request: Request,
) -> SetupStatus:
    _require_setup_draft_access(request)
    existing = SetupInstallRepository(request.app.state.db_path).get_draft()
    password_hash = None
    if body.password is not None:
        password_hash = hash_password(body.password)
    elif existing.password_hash is None:
        raise HTTPException(status_code=422, detail="首次保存 Owner 时必须设置密码")
    try:
        SetupInstallRepository(request.app.state.db_path).save_owner_draft(
            account_id=body.account_id,
            display_name=body.display_name,
            password_hash=password_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _setup_status(request)


@router.put("/setup/draft/offline")
async def save_setup_offline_draft(
    body: SetupOfflineDraftRequest,
    request: Request,
) -> SetupStatus:
    _require_setup_draft_access(request)
    try:
        save_offline_setup_draft(
            request.app.state.db_path,
            use_local_ollama=body.use_local_ollama,
            model_id=body.model_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _setup_status(request)


@router.put("/setup/draft/nest")
async def save_setup_nest_draft(
    body: SetupNestDraftRequest,
    request: Request,
) -> SetupStatus:
    _require_setup_draft_access(request)
    try:
        SetupInstallRepository(request.app.state.db_path).save_nest_draft(
            bed_count=body.bed_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _setup_status(request)


@router.post("/setup/install", status_code=202)
async def confirm_setup_install(
    body: SetupInstallRequest,
    request: Request,
) -> JSONResponse:
    """Lock the draft, create the Owner once, and queue one unified install."""
    _ = body.confirmed
    _require_setup_install_access(request)
    db_path = request.app.state.db_path
    draft_repository = SetupInstallRepository(db_path)
    draft = draft_repository.get_draft()
    if not draft.complete or draft.password_hash is None:
        raise HTTPException(status_code=422, detail="Setup 配置尚未完成")
    was_locked = draft.locked_at is not None
    if not was_locked:
        try:
            draft_repository.lock_draft()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        draft = draft_repository.get_draft()
    try:
        owner_account = create_first_owner_from_hash(db_path, draft)
    except SetupAlreadyCompleteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session_token = create_session(owner_account.user_id, db_path)
    owner_csrf = generate_csrf_token(session_token)
    worker_factory = getattr(request.app.state, "setup_install_worker_factory", None)
    worker = (
        worker_factory(db_path)
        if callable(worker_factory)
        else build_setup_install_worker(db_path)
    )
    record = request.app.state.setup_install_jobs.start(
        db_path=db_path,
        worker=worker,
    )
    response = JSONResponse(
        content=_setup_status(request)
        .model_copy(update={"csrf_token": owner_csrf})
        .model_dump(mode="json"),
        status_code=200 if record.task_status == "completed" else 202,
    )
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=get_session_ttl_seconds(db_path),
    )
    response.delete_cookie(key="setup_token", path="/")
    response.headers["X-CSRF-Token"] = owner_csrf
    return response


@router.get("/setup/ollama-detection")
async def get_setup_ollama_detection(
    owner: dict = RequireOwner,
) -> SetupOllamaDetection:
    """Inspect the saved or documented local Ollama endpoint without installing it."""
    _ = owner
    observation = OllamaSetupService(
        adapter=OllamaPlatformAdapter(),
    ).inspect()
    return SetupOllamaDetection(
        state=observation.probe.state,
        endpoint=observation.probe.endpoint or None,
        version=observation.probe.version,
    )


@router.get("/setup/model-recommendation")
async def get_setup_model_recommendation(
    owner: dict = RequireOwner,
) -> SetupModelRecommendation:
    """Recommend a local model only when the host clears the 4 GiB floor."""
    _ = owner
    memory_gb = get_available_memory_gb()
    profile = recommend_local_profile(memory_gb)
    if profile is None:
        return SetupModelRecommendation(
            memory_gb=memory_gb,
            recommended_model=None,
            ollama_state="absent",
            ollama_endpoint=None,
            installed_models=[],
            recommended_model_available=False,
        )
    observation = OllamaSetupService(
        adapter=OllamaPlatformAdapter(),
    ).inspect()
    recommended_model = f"ollama/{profile.text_model}"
    return SetupModelRecommendation(
        memory_gb=memory_gb,
        recommended_model=recommended_model,
        ollama_state=observation.probe.state,
        ollama_endpoint=observation.probe.endpoint or None,
        installed_models=list(observation.models),
        recommended_model_available=profile.text_model in observation.models,
    )


def _setup_status(request: Request) -> SetupStatus:
    repository = SetupInstallRepository(request.app.state.db_path)
    install = repository.get()
    draft = repository.get_draft()
    owner_exists = _has_owner(request)
    owner_configured = draft.owner_configured or owner_exists
    offline_configured = draft.offline_configured
    nest_configured = draft.nest_configured
    complete = install.status == "completed"
    current_step = (
        4
        if draft.locked_at is not None
        else (
            1
            if not owner_configured
            else 2
            if not offline_configured
            else 3
            if not nest_configured
            else 4
        )
    )
    step_names = (
        "创建 Owner 账号",
        "配置本地离线保障（可选）",
        "设置精灵巢床位",
        "确认并安装",
    )
    step_configured = (owner_configured, offline_configured, nest_configured, complete)
    steps = [
        SetupStepStatus(
            number=number,
            name=step_names[number - 1],
            status=(
                "completed"
                if configured
                else "current"
                if number == current_step
                else "pending"
            ),
            retry_action=(
                "retry_install"
                if number == 4 and install.task_status == "failed"
                else None
            ),
        )
        for number, configured in enumerate(step_configured, start=1)
    ]
    active_phase = install.install_step or 5
    phase_names = {
        1: "owner",
        2: "ollama",
        3: "model",
        4: "emergency_food",
        5: "nest",
    }
    install_status = SetupInstallStatus(
        phase=phase_names[active_phase],
        action_key=install.install_action or "idle",
        state=install.task_status
        if install.task_status in {"idle", "running", "failed", "completed"}
        else "idle",
        progress=install.task_progress,
        error_key="setup.install.failed" if install.task_status == "failed" else None,
    )
    setup_token = request.cookies.get("setup_token")
    session_token = request.cookies.get("session_token")
    csrf_source = setup_token or session_token
    ollama_installed = False
    try:
        adapter = OllamaPlatformAdapter()
        try:
            launch_target, _ = official_launch_target(adapter.platform)
        except RuntimeError:
            launch_target = ""
        observation = adapter.probe(
            OllamaBinding(
                api_base=DEFAULT_OLLAMA_ENDPOINT,
                platform=adapter.platform,
                install_kind="existing-public",
                launch_target=launch_target,
                version="",
            )
        )
        ollama_installed = observation.state in {
            "healthy",
            "stopped",
            "repair_required",
        }
    except (OSError, RuntimeError, ValueError):
        ollama_installed = False
    return SetupStatus(
        need_setup=not complete,
        complete=complete,
        current_step=current_step,
        steps=steps,
        last_error=install.last_error,
        draft=SetupDraftView(
            owner_account_id=draft.owner_account_id,
            display_name=draft.display_name,
            password_configured=draft.password_configured,
            use_local_ollama=draft.use_local_ollama,
            ollama_installed=ollama_installed,
            model_id=draft.model_id,
            bed_count=draft.bed_count,
            owner_configured=draft.owner_configured,
            offline_configured=draft.offline_configured,
            nest_configured=draft.nest_configured,
            locked_at=draft.locked_at,
        ),
        locked=draft.locked_at is not None,
        csrf_token=generate_csrf_token(csrf_source) if csrf_source else None,
        install=install_status,
    )


def _require_setup_draft_access(request: Request) -> None:
    _require_local_setup_client(request)
    if not request.cookies.get("setup_token"):
        raise HTTPException(status_code=403, detail="缺少 Setup token")
    if _has_owner(request):
        raise HTTPException(status_code=409, detail="系统已有 Owner，Setup 草稿已关闭")
    if (
        SetupInstallRepository(request.app.state.db_path).get_draft().locked_at
        is not None
    ):
        raise HTTPException(status_code=409, detail="Setup 配置已锁定")


def _require_setup_install_access(request: Request) -> None:
    _require_local_setup_client(request)
    if not _has_owner(request):
        if not request.cookies.get("setup_token"):
            raise HTTPException(status_code=403, detail="缺少 Setup token")
        return
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=403, detail="需要 Owner 会话")
    principal = verify_session(session_token, request.app.state.db_path)
    if principal is None or principal["role"] != "owner":
        raise HTTPException(status_code=403, detail="需要 Owner 权限")


def _has_owner(request: Request) -> bool:
    return has_owner(request.app.state.db_path)
