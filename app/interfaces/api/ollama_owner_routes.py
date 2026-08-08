"""Management endpoints for the always-present local Ollama card."""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from app.features.accounts.auth import AuthenticatedUser, require_manager
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.ollama_owner import OllamaOwnerService
from app.features.setup.ollama_owner_jobs import OllamaOwnerJobManager, OllamaTask
from app.infrastructure.ollama_platform import (
    OllamaPlatformAdapter,
    OllamaState,
)

from .ollama_owner_models import (
    OllamaInstallRequest,
    OllamaOwnerModelResponse,
    OllamaOwnerStatusResponse,
    OllamaOwnerTaskResponse,
    OllamaPullRequest,
)

router = APIRouter()
_JOBS: Final[OllamaOwnerJobManager] = OllamaOwnerJobManager()
RequireManager = Depends(require_manager)


@router.get("/ollama", response_model=OllamaOwnerStatusResponse)
def get_ollama_status(
    request: Request,
    owner: AuthenticatedUser = RequireManager,
) -> OllamaOwnerStatusResponse:
    _ = owner
    return _status(request)


@router.post("/ollama/install", response_model=OllamaOwnerStatusResponse)
def install_or_connect_ollama(
    body: OllamaInstallRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    owner: AuthenticatedUser = RequireManager,
) -> OllamaOwnerStatusResponse:
    _ = body
    _ = owner
    scope = request.app.state.db_path
    current_task = _JOBS.current(scope)
    if current_task is not None and current_task.state == "running":
        raise HTTPException(status_code=409, detail="当前 Ollama 已有进行中的任务")
    service = _owner_service(request.app.state.db_path)
    observation = service.inspect(task=current_task)
    if observation.probe.state in {"absent", "deleted"}:
        try:
            _JOBS.enqueue(
                scope,
                "install",
                background_tasks,
                lambda: _install_official(scope),
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif observation.probe.state in {"healthy", "stopped"}:
        try:
            service.connect_or_start()
            _JOBS.clear(scope)
        except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=409, detail="已记录的 Ollama 安装需要修复")
    return _status(request)


@router.post("/ollama/start", response_model=OllamaOwnerStatusResponse)
def start_ollama(
    request: Request,
    owner: AuthenticatedUser = RequireManager,
) -> OllamaOwnerStatusResponse:
    _ = owner
    scope = request.app.state.db_path
    current_task = _JOBS.current(scope)
    if current_task is not None and current_task.state == "running":
        raise HTTPException(status_code=409, detail="当前 Ollama 已有进行中的任务")
    try:
        _owner_service(scope).connect_or_start()
        _JOBS.clear(scope)
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _status(request)


@router.post("/ollama/models/pull", response_model=OllamaOwnerStatusResponse)
def pull_ollama_models(
    body: OllamaPullRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    owner: AuthenticatedUser = RequireManager,
) -> OllamaOwnerStatusResponse:
    _ = body.confirmed
    _ = owner
    service = _owner_service(request.app.state.db_path)
    observation = service.inspect(task=_JOBS.current(request.app.state.db_path))
    if observation.probe.state != "healthy":
        raise HTTPException(status_code=409, detail="Ollama 未运行，不能下载模型")
    try:
        _JOBS.enqueue(
            request.app.state.db_path,
            "model_pull",
            background_tasks,
            lambda: service.pull_and_save(tuple(body.model_ids)),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _status(request)


def _status(request: Request) -> OllamaOwnerStatusResponse:
    scope = request.app.state.db_path
    task = _JOBS.current(scope)
    observation = _owner_service(scope).inspect(task=task)
    visible_state = _visible_state(observation.probe.state, task)
    return OllamaOwnerStatusResponse(
        state=visible_state,
        endpoint=observation.probe.endpoint or None,
        version=observation.probe.version,
        memory_gb=observation.memory_gb,
        recommended_model=observation.recommended_model,
        installed_model_count=observation.installed_model_count,
        models=[
            OllamaOwnerModelResponse(
                id=model.id,
                display_name=model.display_name,
                installed=model.installed,
                recommended=model.recommended,
            )
            for model in observation.models
        ],
        task=(
            OllamaOwnerTaskResponse(
                key=task.key,
                state=task.state,
                progress=task.progress,
                error=task.error,
            )
            if task is not None
            else None
        ),
    )


def _visible_state(probe_state: OllamaState, task: OllamaTask | None) -> OllamaState:
    if task is None or task.key == "model_pull":
        return probe_state
    if task.state == "running":
        return "installing"
    if task.state == "failed":
        return "failed"
    return probe_state


def _install_official(db_path: str) -> None:
    OllamaSetupService(
        adapter=OllamaPlatformAdapter(),
        provider_connection_store=_provider_store(db_path),
    ).ensure_for_install(report_action=lambda _action: None)


def _owner_service(db_path: str) -> OllamaOwnerService:
    return OllamaOwnerService(
        adapter=OllamaPlatformAdapter(),
        provider_connection_store=_provider_store(db_path),
    )


def _provider_store(db_path: str) -> ProviderConnectionStore:
    return ProviderConnectionStore(
        final_root_layout(data_home_from_db_path(db_path)).providers_config
    )
