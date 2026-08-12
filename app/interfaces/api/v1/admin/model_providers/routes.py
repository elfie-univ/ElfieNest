"""Versioned administrator routes for model Provider resources."""

from __future__ import annotations

from typing import FrozenSet, Optional, Union, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    AddProviderModelCommand,
    BenchmarkCombination,
    BenchmarkProviderModelsCommand,
    ChangeProviderConnectionLifecycleCommand,
    ConnectionUpdateField,
    CreateProviderConnectionCommand,
    DeleteProviderConnectionCommand,
    DeleteProviderModelCommand,
    GetProviderModelMatrixQuery,
    InspectLocalProviderQuery,
    InstallLocalProviderCommand,
    LifecycleAction,
    ListProviderConnectionsQuery,
    ListProviderProductsQuery,
    LocalProviderStatusResult,
    ModelUpdateField,
    ProviderConnectionNotFound,
    ProviderModelInput,
    ProviderModelNotFound,
    ProviderModelReplacement,
    ProviderProductNotFound,
    ProvidersConflict,
    ProvidersForbidden,
    ProvidersService,
    ProvidersUnavailable,
    ProvidersValidationError,
    PullLocalProviderModelsCommand,
    RefreshProviderModelsCommand,
    ReplaceProviderModelsCommand,
    StartLocalProviderCommand,
    UpdateProviderConnectionCommand,
    UpdateProviderModelCommand,
    ValidateAllProviderModelsCommand,
    VerifyProviderConnectionCommand,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import providers_service
from .models import (
    BenchmarkModelsRequest,
    BenchmarkRunResponse,
    DetailResponse,
    ErrorDetails,
    ErrorItem,
    ErrorResponse,
    LocalProviderInstallRequest,
    LocalProviderModelResponse,
    LocalProviderPullRequest,
    LocalProviderStatusResponse,
    LocalProviderTaskResponse,
    ModelMatrixResponse,
    ModelRefreshResponse,
    ProviderConnectionCreateRequest,
    ProviderConnectionPatchRequest,
    ProviderConnectionResponse,
    ProviderConnectionsResponse,
    ProviderModelPatchRequest,
    ProviderModelResponse,
    ProviderModelsReplaceRequest,
    ProviderModelWriteRequest,
    ProviderProductResponse,
    ProviderProductsResponse,
    ValidationRunResponse,
    VerifyConnectionResponse,
)

router = APIRouter(
    prefix="/api/v1/admin/model-providers",
    tags=["admin-model-providers"],
)
CurrentPrincipal = Depends(require_user)
ProvidersDependency = Depends(providers_service)
RouteResult = Union[
    BenchmarkRunResponse,
    DetailResponse,
    ModelMatrixResponse,
    ModelRefreshResponse,
    ProviderConnectionResponse,
    ProviderConnectionsResponse,
    ProviderModelResponse,
    ProviderProductsResponse,
    ValidationRunResponse,
    VerifyConnectionResponse,
    JSONResponse,
    LocalProviderStatusResponse,
]


@router.get("/ollama", response_model=LocalProviderStatusResponse)
def inspect_local_provider(
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.inspect_local_provider(
            principal,
            InspectLocalProviderQuery(),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return _local_provider_response(result)


@router.post("/ollama/install", response_model=LocalProviderStatusResponse)
def install_local_provider(
    body: LocalProviderInstallRequest,
    background_tasks: BackgroundTasks,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.install_local_provider(
            principal,
            InstallLocalProviderCommand(confirmed=body.confirmed),
            background_tasks,
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return _local_provider_response(result)


@router.post("/ollama/start", response_model=LocalProviderStatusResponse)
def start_local_provider(
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.start_local_provider(
            principal,
            StartLocalProviderCommand(),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return _local_provider_response(result)


@router.post("/ollama/models/pull", response_model=LocalProviderStatusResponse)
def pull_local_provider_models(
    body: LocalProviderPullRequest,
    background_tasks: BackgroundTasks,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.pull_local_models(
            principal,
            PullLocalProviderModelsCommand(tuple(body.model_ids), body.confirmed),
            background_tasks,
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return _local_provider_response(result)


@router.get("/catalog", response_model=ProviderProductsResponse)
def list_products(
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        items = service.list_products(principal, ListProviderProductsQuery())
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderProductsResponse(
        items=tuple(ProviderProductResponse.from_result(item) for item in items)
    )


@router.get("/connections", response_model=ProviderConnectionsResponse)
def list_connections(
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        items = service.list_connections(principal, ListProviderConnectionsQuery())
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderConnectionsResponse(
        items=tuple(ProviderConnectionResponse.from_result(item) for item in items)
    )


@router.post(
    "/connections",
    response_model=ProviderConnectionResponse,
    status_code=201,
)
async def create_connection(
    body: ProviderConnectionCreateRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.create_connection(
            principal,
            CreateProviderConnectionCommand(
                catalog_id=body.catalog_id,
                alias=body.alias,
                api_base=body.api_base,
                api_key=body.api_key,
                api_mode=body.api_mode,
                auth_type=body.auth_type,
                models=tuple(_model_input(item) for item in body.models),
                verify=body.verify,
                refresh_models=body.refresh_models,
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderConnectionResponse.from_result(result)


@router.patch(
    "/connections/{connection_id}",
    response_model=ProviderConnectionResponse,
)
async def update_connection(
    connection_id: str,
    body: ProviderConnectionPatchRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    fields = cast(
        FrozenSet[ConnectionUpdateField],
        frozenset(body.model_fields_set)
        & {"alias", "api_base", "api_key", "api_mode", "auth_type", "models"},
    )
    try:
        result = await service.update_connection(
            principal,
            UpdateProviderConnectionCommand(
                connection_id=connection_id,
                fields=fields,
                alias=body.alias,
                api_base=body.api_base,
                api_key=body.api_key,
                api_mode=body.api_mode,
                auth_type=body.auth_type,
                models=(
                    None
                    if body.models is None
                    else tuple(_model_input(item) for item in body.models)
                ),
                verify=body.verify,
                refresh_models=body.refresh_models,
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderConnectionResponse.from_result(result)


@router.delete(
    "/connections/{connection_id}",
    response_model=DetailResponse,
)
def delete_connection(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        service.delete_connection(
            principal,
            DeleteProviderConnectionCommand(connection_id),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return DetailResponse(detail=f"Provider connection '{connection_id}' deleted")


@router.post(
    "/connections/{connection_id}/enable",
    response_model=ProviderConnectionResponse,
)
def enable_connection(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    return _lifecycle(connection_id, "enable", principal, service)


@router.post(
    "/connections/{connection_id}/disable",
    response_model=ProviderConnectionResponse,
)
def disable_connection(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    return _lifecycle(connection_id, "disable", principal, service)


@router.post(
    "/connections/{connection_id}/archive",
    response_model=ProviderConnectionResponse,
)
def archive_connection(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    return _lifecycle(connection_id, "archive", principal, service)


@router.post(
    "/connections/{connection_id}/restore",
    response_model=ProviderConnectionResponse,
)
def restore_connection(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    return _lifecycle(connection_id, "restore", principal, service)


@router.post(
    "/connections/{connection_id}/verify",
    response_model=VerifyConnectionResponse,
)
async def verify_connection(
    connection_id: str,
    force_full: bool = Query(default=False),
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.verify_connection(
            principal,
            VerifyProviderConnectionCommand(connection_id, force_full),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return VerifyConnectionResponse.from_result(result)


@router.post(
    "/connections/{connection_id}/models/refresh",
    response_model=ModelRefreshResponse,
)
async def refresh_models(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.refresh_models(
            principal,
            RefreshProviderModelsCommand(connection_id),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ModelRefreshResponse.from_result(result)


@router.post(
    "/connections/{connection_id}/models",
    response_model=ProviderModelResponse,
    status_code=201,
)
def add_model(
    connection_id: str,
    body: ProviderModelWriteRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.add_model(
            principal,
            AddProviderModelCommand(connection_id, _model_input(body)),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderModelResponse.from_result(result)


@router.put(
    "/connections/{connection_id}/models",
    response_model=ProviderConnectionResponse,
)
def replace_models(
    connection_id: str,
    body: ProviderModelsReplaceRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.replace_models(
            principal,
            ReplaceProviderModelsCommand(
                connection_id=connection_id,
                models=tuple(
                    ProviderModelReplacement(
                        **vars(_model_input(item)),
                        original_model_id=item.original_id,
                        hidden=item.hidden,
                    )
                    for item in body.models
                ),
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderConnectionResponse.from_result(result)


@router.patch(
    "/connections/{connection_id}/models/{model_id:path}",
    response_model=ProviderModelResponse,
)
def update_model(
    connection_id: str,
    model_id: str,
    body: ProviderModelPatchRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    fields = cast(FrozenSet[ModelUpdateField], frozenset(body.model_fields_set))
    try:
        result = service.update_model(
            principal,
            UpdateProviderModelCommand(
                connection_id=connection_id,
                model_id=model_id,
                fields=fields,
                display_name=body.display_name,
                canonical_model_id=body.canonical_model_id,
                context_window_tokens=body.context_window_tokens,
                max_output_tokens=body.max_output_tokens,
                supports_tools=body.supports_tools,
                supports_vision=body.supports_vision,
                supports_reasoning=body.supports_reasoning,
                hidden=body.hidden,
                retired=body.retired,
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderModelResponse.from_result(result)


@router.delete(
    "/connections/{connection_id}/models/{model_id:path}",
    response_model=DetailResponse,
)
def delete_model(
    connection_id: str,
    model_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        service.delete_model(
            principal,
            DeleteProviderModelCommand(connection_id, model_id),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return DetailResponse(detail=f"Provider model '{model_id}' deleted")


@router.get("/model-matrix", response_model=ModelMatrixResponse)
def model_matrix(
    as_of: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.get_model_matrix(
            principal,
            GetProviderModelMatrixQuery(as_of=as_of, run_id=run_id),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ModelMatrixResponse.from_result(result)


@router.post("/model-benchmarks", response_model=BenchmarkRunResponse)
async def benchmark_models(
    body: BenchmarkModelsRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.benchmark_models(
            principal,
            BenchmarkProviderModelsCommand(
                combinations=tuple(
                    BenchmarkCombination(item.connection_id, item.model_id)
                    for item in body.combinations
                )
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return BenchmarkRunResponse.from_result(result)


@router.post("/model-validations", response_model=ValidationRunResponse)
async def validate_all(
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    async def cancelled() -> bool:
        return await request.is_disconnected()

    try:
        result = await service.validate_all(
            principal,
            ValidateAllProviderModelsCommand(),
            cancelled,
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ValidationRunResponse.from_result(result)


def _lifecycle(
    connection_id: str,
    action: LifecycleAction,
    principal: AccountPrincipal,
    service: ProvidersService,
) -> RouteResult:
    try:
        result = service.change_lifecycle(
            principal,
            ChangeProviderConnectionLifecycleCommand(
                connection_id,
                action,
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderConnectionResponse.from_result(result)


def _model_input(body: ProviderModelWriteRequest) -> ProviderModelInput:
    return ProviderModelInput(
        model_id=body.id,
        display_name=body.display_name,
        canonical_model_id=body.canonical_model_id,
        context_window_tokens=body.context_window_tokens,
        max_output_tokens=body.max_output_tokens,
        supports_tools=body.supports_tools,
        supports_vision=body.supports_vision,
        supports_reasoning=body.supports_reasoning,
    )


def _local_provider_response(
    result: LocalProviderStatusResult,
) -> LocalProviderStatusResponse:
    return LocalProviderStatusResponse(
        state=result.state,
        endpoint=result.endpoint,
        version=result.version,
        memory_gb=result.memory_gb,
        recommended_model=result.recommended_model,
        installed_model_count=result.installed_model_count,
        models=tuple(
            LocalProviderModelResponse(
                id=item.model_id,
                display_name=item.display_name,
                installed=item.installed,
                recommended=item.recommended,
            )
            for item in result.models
        ),
        task=(
            LocalProviderTaskResponse(**vars(result.task))
            if result.task is not None
            else None
        ),
    )


_PROVIDER_ERRORS = (
    ProviderConnectionNotFound,
    ProviderModelNotFound,
    ProviderProductNotFound,
    ProvidersConflict,
    ProvidersForbidden,
    ProvidersUnavailable,
    ProvidersValidationError,
)


def _error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "model_providers_unavailable"
    if isinstance(error, ProvidersForbidden):
        status_code = 403
        code = "model_providers_forbidden"
    elif isinstance(error, ProviderProductNotFound):
        status_code = 404
        code = "provider_product_not_found"
    elif isinstance(error, ProviderConnectionNotFound):
        status_code = 404
        code = "provider_connection_not_found"
    elif isinstance(error, ProviderModelNotFound):
        status_code = 404
        code = "provider_model_not_found"
    elif isinstance(error, ProvidersValidationError):
        status_code = 422
        code = "invalid_model_provider"
    elif isinstance(error, ProvidersConflict):
        status_code = 409
        code = "model_provider_conflict"
    payload = ErrorResponse(
        error=ErrorItem(
            code=code,
            message=str(error),
            details=ErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("router",)
