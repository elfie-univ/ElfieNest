"""Versioned administrator routes for model Provider resources."""

from __future__ import annotations

from datetime import timedelta
from typing import FrozenSet, Optional, Union, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal, is_manager
from app.features.configuration import (
    AddProviderModelCommand,
    BenchmarkCombination,
    BenchmarkProviderModelsCommand,
    CapabilityName,
    ChangeProviderConnectionLifecycleCommand,
    CleanupObsoleteProviderModelsCommand,
    CompleteProviderOAuthLoginCommand,
    ConnectionUpdateField,
    CreateProviderConnectionCommand,
    DeleteProviderConnectionCommand,
    DeleteProviderModelCommand,
    GetProviderModelMatrixQuery,
    InspectLocalProviderQuery,
    InstallLocalProviderCommand,
    LifecycleAction,
    ListObsoleteProviderModelsQuery,
    ListProviderConnectionsQuery,
    ListProviderProductsQuery,
    LocalProviderStatusResult,
    ModelUpdateField,
    ProbeProviderModelCapabilitiesCommand,
    ProviderAvailabilityPort,
    ProviderConnectionNotFound,
    ProviderConnectionResult,
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
    StartProviderOAuthLoginCommand,
    UpdateProviderConnectionCommand,
    UpdateProviderModelCommand,
    ValidateAllProviderModelsCommand,
    VerifyProviderConnectionCommand,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import provider_availability, providers_service
from .models import (
    BenchmarkModelsRequest,
    BenchmarkRunResponse,
    DetailResponse,
    ErrorDetails,
    ErrorItem,
    ErrorResponse,
    LocalModelCountsResponse,
    LocalProviderInstallRequest,
    LocalProviderModelResponse,
    LocalProviderPullRequest,
    LocalProviderStatusResponse,
    LocalProviderTaskResponse,
    ModelMatrixResponse,
    ModelRefreshResponse,
    ProviderCapabilityProbeItemResponse,
    ProviderCapabilityProbeRequest,
    ProviderCapabilityProbeResponse,
    ProviderConnectionCreateRequest,
    ProviderConnectionPatchRequest,
    ProviderConnectionResponse,
    ProviderConnectionsResponse,
    ProviderModelAvailabilityListResponse,
    ProviderModelAvailabilityResponse,
    ProviderModelPatchRequest,
    ProviderModelResponse,
    ProviderModelsReplaceRequest,
    ProviderModelWriteRequest,
    ProviderOAuthLoginCompleteRequest,
    ProviderOAuthLoginStartRequest,
    ProviderOAuthLoginStartResponse,
    ProviderOAuthLoginStatusResponse,
    ProviderObsoleteCleanupRequest,
    ProviderObsoleteModelResponse,
    ProviderObsoleteModelsResponse,
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
ModelAvailabilityReferences = Query(default=[], max_length=256)
ProviderAvailabilityDependency = Depends(provider_availability)
RouteResult = Union[
    BenchmarkRunResponse,
    DetailResponse,
    ModelMatrixResponse,
    ModelRefreshResponse,
    ProviderConnectionResponse,
    ProviderConnectionsResponse,
    ProviderCapabilityProbeResponse,
    ProviderModelResponse,
    ProviderModelAvailabilityListResponse,
    ProviderObsoleteModelsResponse,
    ProviderProductsResponse,
    ValidationRunResponse,
    VerifyConnectionResponse,
    JSONResponse,
    LocalProviderStatusResponse,
    ProviderOAuthLoginStartResponse,
    ProviderOAuthLoginStatusResponse,
]


@router.get("/ollama", response_model=LocalProviderStatusResponse)
def inspect_local_provider(
    background_tasks: BackgroundTasks,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.inspect_local_provider(
            principal,
            InspectLocalProviderQuery(),
            background_tasks,
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


@router.post("/ollama/verify", response_model=LocalProviderStatusResponse)
async def verify_local_provider_models(
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.verify_local_models(principal)
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


@router.post("/oauth-logins", response_model=ProviderOAuthLoginStartResponse)
async def start_oauth_login(
    body: ProviderOAuthLoginStartRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.start_oauth_login(
            principal, StartProviderOAuthLoginCommand(body.catalog_id)
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderOAuthLoginStartResponse.from_result(result)


@router.post(
    "/oauth-logins/{login_id}/complete",
    response_model=ProviderOAuthLoginStatusResponse,
)
async def complete_oauth_login(
    login_id: str,
    body: ProviderOAuthLoginCompleteRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.complete_oauth_login(
            principal,
            CompleteProviderOAuthLoginCommand(body.catalog_id, login_id, body.alias),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderOAuthLoginStatusResponse.from_result(result)


@router.post(
    "/connections",
    response_model=ProviderConnectionResponse,
    status_code=201,
)
async def create_connection(
    body: ProviderConnectionCreateRequest,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        _require_setup_only_deferred_validation(request, body.defer_validation)
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
                defer_validation=body.defer_validation,
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
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    fields = cast(
        FrozenSet[ConnectionUpdateField],
        frozenset(body.model_fields_set)
        & {"alias", "api_base", "api_key", "api_mode", "auth_type", "models"},
    )
    try:
        _require_setup_only_deferred_validation(request, body.defer_validation)
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
                defer_validation=body.defer_validation,
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
                        fields=frozenset(item.model_fields_set),
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
                supports_structured_output=body.supports_structured_output,
                request_profile_id=body.request_profile_id,
                request_profile_version=body.request_profile_version,
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


@router.post(
    "/connections/{connection_id}/models/{model_id:path}/capability-probes",
    response_model=ProviderCapabilityProbeResponse,
)
async def probe_model_capabilities(
    connection_id: str,
    model_id: str,
    body: ProviderCapabilityProbeRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = await service.probe_capabilities(
            principal,
            ProbeProviderModelCapabilitiesCommand(
                connection_id=connection_id,
                model_id=model_id,
                capabilities=tuple(body.capabilities),
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderCapabilityProbeResponse(
        reference=result.reference,
        results=tuple(
            ProviderCapabilityProbeItemResponse(**vars(item)) for item in result.results
        ),
    )


@router.get(
    "/connections/{connection_id}/models/obsolete",
    response_model=ProviderObsoleteModelsResponse,
)
def list_obsolete_models(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        items = service.list_obsolete_models(
            principal,
            ListObsoleteProviderModelsQuery(connection_id),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    return ProviderObsoleteModelsResponse(
        items=tuple(
            ProviderObsoleteModelResponse(
                model=ProviderModelResponse.from_result(item.model),
                eligible=item.eligible,
                reason=item.reason,
                last_production_at=item.last_production_at,
            )
            for item in items
        )
    )


@router.post(
    "/connections/{connection_id}/models/cleanup-obsolete",
    response_model=DetailResponse,
)
def cleanup_all_obsolete_models(
    connection_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    """Compatibility entry point for the original Owner cleanup action.

    The model-management route below supports explicit selections.  This
    route intentionally keeps the original no-body action for callers that
    want the service to remove every currently eligible source-managed model.
    """
    try:
        result = service.cleanup_obsolete_models(
            principal,
            CleanupObsoleteProviderModelsCommand(connection_id),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    model_ids = tuple(getattr(result, "model_ids", ()))
    cleaned = ", ".join(model_ids) if model_ids else "none"
    return DetailResponse(
        detail=f"Obsolete Provider models cleaned for '{connection_id}': {cleaned}"
    )


@router.post(
    "/connections/{connection_id}/models/obsolete/cleanup",
    response_model=ProviderConnectionResponse,
)
def cleanup_obsolete_models(
    connection_id: str,
    body: ProviderObsoleteCleanupRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ProvidersService = ProvidersDependency,
) -> RouteResult:
    try:
        result = service.cleanup_obsolete_models(
            principal,
            CleanupObsoleteProviderModelsCommand(
                connection_id=connection_id,
                model_ids=tuple(body.model_ids),
            ),
        )
    except _PROVIDER_ERRORS as error:
        return _error_response(error)
    assert isinstance(result, ProviderConnectionResult)
    return ProviderConnectionResponse.from_result(result)


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


@router.get(
    "/availability",
    response_model=ProviderModelAvailabilityListResponse,
)
def model_availability(
    reference: list[str] = ModelAvailabilityReferences,
    principal: AccountPrincipal = CurrentPrincipal,
    availability: ProviderAvailabilityPort = ProviderAvailabilityDependency,
) -> ProviderModelAvailabilityListResponse:
    _require_manager_for_probe(principal)
    items = availability.get_many(tuple(reference))
    return ProviderModelAvailabilityListResponse(
        items=tuple(
            ProviderModelAvailabilityResponse.from_result(item) for item in items
        )
    )


@router.post(
    "/availability/ensure",
    response_model=ProviderModelAvailabilityResponse,
)
def ensure_model_availability(
    reference: str = Query(..., min_length=3),
    max_age_seconds: int = Query(default=86400, ge=0, le=604800),
    capability: Optional[CapabilityName] = Query(default=None),  # noqa: B008
    principal: AccountPrincipal = CurrentPrincipal,
    availability: ProviderAvailabilityPort = ProviderAvailabilityDependency,
) -> ProviderModelAvailabilityResponse:
    _require_manager_for_probe(principal)
    item = availability.ensure(
        reference,
        max_age=timedelta(seconds=max_age_seconds),
        allow_probe=True,
        capability=capability,
    )
    return ProviderModelAvailabilityResponse.from_result(item)


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
        supports_structured_output=body.supports_structured_output,
        request_profile_id=body.request_profile_id,
        request_profile_version=body.request_profile_version,
    )


def _local_provider_response(
    result: LocalProviderStatusResult,
) -> LocalProviderStatusResponse:
    return LocalProviderStatusResponse(
        state=result.state,
        checked_at=result.checked_at,
        endpoint=result.endpoint,
        version=result.version,
        memory_gb=result.memory_gb,
        recommended_model=result.recommended_model,
        installed_model_count=result.installed_model_count,
        model_counts=LocalModelCountsResponse.from_result(result.model_counts),
        models=tuple(
            LocalProviderModelResponse(
                id=item.model_id,
                display_name=item.display_name,
                installed=item.installed,
                recommended=item.recommended,
                availability_status=item.availability_status,
                available=item.available,
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


def _require_manager_for_probe(principal: AccountPrincipal) -> None:
    if not is_manager(principal.role):
        raise HTTPException(status_code=403, detail="Provider 可用性查询需要管理员权限")


def _require_setup_only_deferred_validation(
    request: Request, defer_validation: bool
) -> None:
    if defer_validation and not request.cookies.get("setup_token"):
        raise ProvidersValidationError("defer_validation 仅允许 Setup 流程使用")


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
