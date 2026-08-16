"""Versioned administrator Food package routes."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.configuration import food
from app.interfaces.api.v1.auth import require_user

from .dependencies import food_service
from .models import (
    FoodCatalogResponse,
    FoodCreateResponse,
    FoodErrorDetails,
    FoodErrorItem,
    FoodErrorResponse,
    FoodGenerationPreviewRequest,
    FoodGenerationPreviewResponse,
    FoodPackageResponse,
    FoodPackageWriteRequest,
    FoodUpdateResponse,
)

router = APIRouter(prefix="/api/v1/admin/food-packages", tags=["admin-food-packages"])
CurrentPrincipal = Depends(require_user)
FoodDependency = Depends(food_service)
_FOOD_ERRORS = (
    food.FoodConflict,
    food.FoodForbidden,
    food.FoodNotFound,
    food.FoodUnavailable,
    food.FoodValidationError,
)


@router.get("", response_model=FoodCatalogResponse)
def list_food_packages(
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[FoodCatalogResponse, JSONResponse]:
    try:
        result = service.list_packages(principal, food.ListFoodPackagesQuery())
    except (food.FoodForbidden, food.FoodUnavailable) as error:
        return _error_response(error)
    return FoodCatalogResponse.from_result(result)


@router.post("", status_code=201, response_model=FoodCreateResponse)
def create_food_package(
    body: FoodPackageWriteRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[FoodCreateResponse, JSONResponse]:
    try:
        result = service.create_package(
            principal,
            food.CreateFoodPackageCommand(
                display_name=body.display_name,
                enabled=body.enabled,
                roles=_roles_input(body),
                visibility_mode=body.visibility_mode,
                visible_user_ids=body.visible_user_ids,
                required_roles=body.required_roles or (),
            ),
        )
    except _FOOD_ERRORS as error:
        return _error_response(error)
    return FoodCreateResponse.from_result(result)


@router.post("/generation-preview", response_model=FoodGenerationPreviewResponse)
def preview_new_food_package(
    body: FoodGenerationPreviewRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[FoodGenerationPreviewResponse, JSONResponse]:
    return _preview(None, body, principal, service)


@router.put("/{food_id}", response_model=FoodUpdateResponse)
def update_food_package(
    food_id: str,
    body: FoodPackageWriteRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[FoodUpdateResponse, JSONResponse]:
    try:
        result = service.update_package(
            principal,
            food.UpdateFoodPackageCommand(
                food_id=food_id,
                display_name=body.display_name,
                enabled=body.enabled,
                roles=_roles_input(body),
                visibility_mode=body.visibility_mode,
                visible_user_ids=body.visible_user_ids,
                required_roles=body.required_roles,
            ),
        )
    except _FOOD_ERRORS as error:
        return _error_response(error)
    return FoodUpdateResponse.from_result(result)


@router.post(
    "/{food_id}/generation-preview",
    response_model=FoodGenerationPreviewResponse,
)
def preview_existing_food_package(
    food_id: str,
    body: FoodGenerationPreviewRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[FoodGenerationPreviewResponse, JSONResponse]:
    return _preview(food_id, body, principal, service)


@router.post("/{food_id}/{action}", response_model=FoodPackageResponse)
def change_food_package_lifecycle(
    food_id: str,
    action: food.FoodLifecycleAction,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[FoodPackageResponse, JSONResponse]:
    try:
        result = service.change_lifecycle(
            principal,
            food.ChangeFoodLifecycleCommand(food_id=food_id, action=action),
        )
    except _FOOD_ERRORS as error:
        return _error_response(error)
    return FoodPackageResponse.from_result(result)


@router.delete("/{food_id}", response_model=FoodCatalogResponse)
def delete_food_package(
    food_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[FoodCatalogResponse, JSONResponse]:
    try:
        result = service.delete_package(
            principal,
            food.DeleteFoodPackageCommand(food_id=food_id),
        )
    except _FOOD_ERRORS as error:
        return _error_response(error)
    return FoodCatalogResponse.from_result(result)


def _preview(
    food_id: str | None,
    body: FoodGenerationPreviewRequest,
    principal: AccountPrincipal,
    service: food.FoodService,
) -> Union[FoodGenerationPreviewResponse, JSONResponse]:
    try:
        result = service.preview_generation(
            principal,
            food.PreviewFoodGenerationCommand(
                food_id=food_id,
                display_name=body.display_name,
                connection_ids=body.connection_ids,
                local_first=body.local_first,
                allow_remote=body.allow_remote,
                visibility_mode=body.visibility_mode,
                visible_user_ids=body.visible_user_ids,
            ),
        )
    except _FOOD_ERRORS as error:
        return _error_response(error)
    return FoodGenerationPreviewResponse.from_result(result)


def _roles_input(body: FoodPackageWriteRequest) -> food.FoodRolesInput:
    return food.FoodRolesInput(
        primary=_role_model(body.roles.primary),
        reasoning=_role_model(body.roles.reasoning),
        vision=_role_model(body.roles.vision),
        tool=_role_model(body.roles.tool),
        fallback=_role_model(body.roles.fallback),
    )


def _role_model(value: object) -> str | None:
    model = getattr(value, "model", None)
    return model if isinstance(model, str) else None


def _error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "food_unavailable"
    if isinstance(error, food.FoodForbidden):
        status_code = 403
        code = "food_forbidden"
    elif isinstance(error, food.FoodNotFound):
        status_code = 404
        code = "food_not_found"
    elif isinstance(error, food.FoodConflict):
        status_code = 409
        code = "food_conflict"
    elif isinstance(error, food.FoodValidationError):
        status_code = 422
        code = "invalid_food"
    payload = FoodErrorResponse(
        error=FoodErrorItem(
            code=code,
            message=str(error),
            details=FoodErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("router",)
