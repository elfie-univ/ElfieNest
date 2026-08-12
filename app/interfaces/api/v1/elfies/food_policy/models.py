"""Strict HTTP DTOs for an Elfie's Food policy resource."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.features.configuration import food


class MainFoodPolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_food_id: str = Field(min_length=1)


class ElfieFoodOptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_id: str
    display_name: str


class MainFoodPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_food_id: str
    effective_main_food_id: str
    main_food_options: tuple[ElfieFoodOptionResponse, ...]
    main_food_unavailable: bool

    @classmethod
    def from_result(cls, policy: food.MainFoodPolicyResult) -> MainFoodPolicyResponse:
        return cls(
            main_food_id=policy.main_food_id,
            effective_main_food_id=policy.effective_main_food_id,
            main_food_options=tuple(
                ElfieFoodOptionResponse(
                    food_id=item.food_id,
                    display_name=item.display_name,
                )
                for item in policy.main_food_options
            ),
            main_food_unavailable=policy.main_food_unavailable,
        )


class ElfieFoodErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ElfieFoodErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: ElfieFoodErrorDetails


class ElfieFoodErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ElfieFoodErrorItem


__all__ = tuple(name for name in globals() if name.endswith(("Request", "Response")))
