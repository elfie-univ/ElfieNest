"""Strict HTTP DTOs for administrator Food package resources."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, cast

from pydantic import BaseModel, ConfigDict, Field

from app.features.configuration import food as food_feature

StrictUserId = Annotated[int, Field(strict=True, gt=0)]
RequiredFoodRole = Literal["reasoning", "vision", "tool"]


class FoodRoleAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)


class FoodRolesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: Optional[FoodRoleAssignmentRequest] = None
    reasoning: Optional[FoodRoleAssignmentRequest] = None
    vision: Optional[FoodRoleAssignmentRequest] = None
    tool: Optional[FoodRoleAssignmentRequest] = None
    fallback: Optional[FoodRoleAssignmentRequest] = None


class FoodPackageWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    enabled: bool = Field(default=False, strict=True)
    roles: FoodRolesRequest
    visibility_mode: Literal["global", "users"] = "global"
    visible_user_ids: tuple[StrictUserId, ...] = ()
    required_roles: Optional[tuple[RequiredFoodRole, ...]] = None


class FoodGenerationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_ids: tuple[str, ...]
    local_first: bool = Field(strict=True)
    allow_remote: bool = Field(strict=True)
    visibility_mode: Literal["global", "users"] = "global"
    visible_user_ids: tuple[StrictUserId, ...] = ()
    display_name: Optional[str] = Field(default=None, min_length=1)


class FoodRoleAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str


class FoodRolesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: Optional[FoodRoleAssignmentResponse]
    reasoning: Optional[FoodRoleAssignmentResponse]
    vision: Optional[FoodRoleAssignmentResponse]
    tool: Optional[FoodRoleAssignmentResponse]
    fallback: Optional[FoodRoleAssignmentResponse]

    @classmethod
    def from_result(cls, roles: food_feature.FoodRolesResult) -> FoodRolesResponse:
        return cls(
            primary=_assignment(roles.primary),
            reasoning=_assignment(roles.reasoning),
            vision=_assignment(roles.vision),
            tool=_assignment(roles.tool),
            fallback=_assignment(roles.fallback),
        )


class FoodPackageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    system_role: Optional[Literal["emergency", "common"]]
    enabled: bool
    archived: bool
    visibility_mode: Literal["global", "users"]
    visible_user_ids: tuple[int, ...]
    roles: FoodRolesResponse
    health: str
    locality: str
    latest_evidence_at: Optional[str]
    required_roles: tuple[RequiredFoodRole, ...] = ()

    @classmethod
    def from_result(cls, result: food_feature.FoodPackageResult) -> FoodPackageResponse:
        return cls(
            key=result.food_id,
            display_name=result.display_name,
            system_role=result.system_role,
            enabled=result.enabled,
            archived=result.archived,
            visibility_mode=result.visibility_mode,
            visible_user_ids=result.visible_user_ids,
            roles=FoodRolesResponse.from_result(result.roles),
            health=result.health,
            locality=result.locality,
            latest_evidence_at=result.latest_evidence_at,
            required_roles=cast(tuple[RequiredFoodRole, ...], result.required_roles),
        )


class EligibleFoodModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str
    display_name: str
    local: bool
    capabilities: tuple[str, ...]


class FoodCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    global_default_food_id: str
    global_emergency_food_id: str
    packages: tuple[FoodPackageResponse, ...]
    eligible_models: tuple[EligibleFoodModelResponse, ...]

    @classmethod
    def from_result(
        cls, catalog: food_feature.FoodCatalogResult
    ) -> FoodCatalogResponse:
        return cls(
            version=catalog.version,
            global_default_food_id=catalog.global_default_food_id,
            global_emergency_food_id=catalog.global_emergency_food_id,
            packages=tuple(
                FoodPackageResponse.from_result(item) for item in catalog.packages
            ),
            eligible_models=tuple(
                EligibleFoodModelResponse(
                    reference=item.reference,
                    display_name=item.display_name,
                    local=item.local,
                    capabilities=item.capabilities,
                )
                for item in catalog.eligible_models
            ),
        )


class FoodCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food: FoodPackageResponse
    catalog: FoodCatalogResponse

    @classmethod
    def from_result(
        cls, result: food_feature.FoodPackageMutationResult
    ) -> FoodCreateResponse:
        if result.catalog is None:
            raise TypeError("Create result requires a catalog")
        return cls(
            food=FoodPackageResponse.from_result(result.food),
            catalog=FoodCatalogResponse.from_result(result.catalog),
        )


class FoodUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food: FoodPackageResponse
    warnings: tuple[str, ...]

    @classmethod
    def from_result(
        cls, result: food_feature.FoodPackageMutationResult
    ) -> FoodUpdateResponse:
        return cls(
            food=FoodPackageResponse.from_result(result.food),
            warnings=result.warnings,
        )


class FoodGenerationChangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    old_model: Optional[str]
    new_model: Optional[str]


class FoodGenerationCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    enabled: bool
    roles: FoodRolesResponse


class FoodGenerationPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_id: Optional[str]
    candidate: FoodGenerationCandidateResponse
    changes: tuple[FoodGenerationChangeResponse, ...]
    warnings: tuple[str, ...]
    has_changes: bool

    @classmethod
    def from_result(
        cls,
        result: food_feature.FoodGenerationPreviewResult,
    ) -> FoodGenerationPreviewResponse:
        return cls(
            food_id=result.food_id,
            candidate=FoodGenerationCandidateResponse(
                display_name=result.candidate.display_name,
                enabled=result.candidate.enabled,
                roles=FoodRolesResponse.from_result(result.candidate.roles),
            ),
            changes=tuple(
                FoodGenerationChangeResponse(
                    role=item.role,
                    old_model=item.old_model,
                    new_model=item.new_model,
                )
                for item in result.changes
            ),
            warnings=result.warnings,
            has_changes=result.has_changes,
        )


class FoodErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FoodErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: FoodErrorDetails


class FoodErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: FoodErrorItem


def _assignment(value: object) -> Optional[FoodRoleAssignmentResponse]:
    model = getattr(value, "model", None)
    return (
        None if not isinstance(model, str) else FoodRoleAssignmentResponse(model=model)
    )


__all__ = tuple(name for name in globals() if name.endswith(("Request", "Response")))
