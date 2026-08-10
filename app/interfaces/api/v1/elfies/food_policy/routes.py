"""Versioned member routes for an Elfie's Food policy."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.configuration import food
from app.interfaces.api.v1.auth import require_user

from .dependencies import food_service
from .models import (
    ElfieFoodErrorDetails,
    ElfieFoodErrorItem,
    ElfieFoodErrorResponse,
    MainFoodPolicyResponse,
    MainFoodPolicyUpdateRequest,
)

router = APIRouter(
    prefix="/api/v1/elfies/{elfie_id}/food-policy",
    tags=["elfie-food-policy"],
)
CurrentPrincipal = Depends(require_user)
FoodDependency = Depends(food_service)


@router.get("", response_model=MainFoodPolicyResponse)
def get_elfie_food_policy(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[MainFoodPolicyResponse, JSONResponse]:
    try:
        result = service.get_elfie_policy(
            principal,
            food.GetMainFoodPolicyQuery(elfie_id=elfie_id),
        )
    except _FOOD_POLICY_ERRORS as error:
        return _error_response(error)
    return MainFoodPolicyResponse.from_result(result)


@router.put("", response_model=MainFoodPolicyResponse)
def update_elfie_food_policy(
    elfie_id: str,
    body: MainFoodPolicyUpdateRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: food.FoodService = FoodDependency,
) -> Union[MainFoodPolicyResponse, JSONResponse]:
    try:
        result = service.update_elfie_policy(
            principal,
            food.UpdateMainFoodPolicyCommand(
                elfie_id=elfie_id,
                main_food_id=body.main_food_id,
            ),
        )
    except _FOOD_POLICY_ERRORS as error:
        return _error_response(error)
    return MainFoodPolicyResponse.from_result(result)


def _error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "food_unavailable"
    if isinstance(error, food.FoodForbidden):
        status_code = 403
        code = "food_forbidden"
    elif isinstance(error, food.FoodNotFound):
        status_code = 404
        code = "elfie_food_policy_not_found"
    elif isinstance(error, food.FoodValidationError):
        status_code = 422
        code = "invalid_elfie_food_policy"
    payload = ElfieFoodErrorResponse(
        error=ElfieFoodErrorItem(
            code=code,
            message=str(error),
            details=ElfieFoodErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


_FOOD_POLICY_ERRORS = (
    food.FoodForbidden,
    food.FoodNotFound,
    food.FoodUnavailable,
    food.FoodValidationError,
)

__all__ = ("router",)
