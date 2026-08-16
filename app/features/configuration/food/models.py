"""Commands, queries and results owned by Food configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .port_models import FoodSystemRole, FoodVisibilityMode

FoodLifecycleAction = Literal["enable", "disable", "archive", "restore"]


@dataclass(frozen=True)
class FoodRolesInput:
    primary: str | None = None
    reasoning: str | None = None
    vision: str | None = None
    tool: str | None = None
    fallback: str | None = None


@dataclass(frozen=True)
class ListFoodPackagesQuery:
    pass


@dataclass(frozen=True)
class CreateFoodPackageCommand:
    display_name: str
    enabled: bool
    roles: FoodRolesInput
    visibility_mode: FoodVisibilityMode
    visible_user_ids: tuple[int, ...]
    required_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpdateFoodPackageCommand:
    food_id: str
    display_name: str
    enabled: bool
    roles: FoodRolesInput
    visibility_mode: FoodVisibilityMode
    visible_user_ids: tuple[int, ...]
    required_roles: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PreviewFoodGenerationCommand:
    connection_ids: tuple[str, ...]
    local_first: bool
    allow_remote: bool
    visibility_mode: FoodVisibilityMode
    visible_user_ids: tuple[int, ...]
    food_id: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class ChangeFoodLifecycleCommand:
    food_id: str
    action: FoodLifecycleAction


@dataclass(frozen=True)
class DeleteFoodPackageCommand:
    food_id: str


@dataclass(frozen=True)
class GetMainFoodPolicyQuery:
    elfie_id: str


@dataclass(frozen=True)
class UpdateMainFoodPolicyCommand:
    elfie_id: str
    main_food_id: str


@dataclass(frozen=True)
class ResolveElfieFoodQuery:
    elfie_id: str


@dataclass(frozen=True)
class FoodRoleAssignmentResult:
    model: str


@dataclass(frozen=True)
class FoodRolesResult:
    primary: FoodRoleAssignmentResult | None
    reasoning: FoodRoleAssignmentResult | None
    vision: FoodRoleAssignmentResult | None
    tool: FoodRoleAssignmentResult | None
    fallback: FoodRoleAssignmentResult | None


@dataclass(frozen=True)
class FoodPackageResult:
    food_id: str
    display_name: str
    system_role: FoodSystemRole | None
    enabled: bool
    archived: bool
    visibility_mode: FoodVisibilityMode
    visible_user_ids: tuple[int, ...]
    roles: FoodRolesResult
    health: str
    locality: str
    latest_evidence_at: str | None
    required_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class EligibleFoodModelResult:
    reference: str
    display_name: str
    local: bool
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class FoodCatalogResult:
    version: int
    global_default_food_id: str
    global_emergency_food_id: str
    packages: tuple[FoodPackageResult, ...]
    eligible_models: tuple[EligibleFoodModelResult, ...]


@dataclass(frozen=True)
class FoodPackageMutationResult:
    food: FoodPackageResult
    catalog: FoodCatalogResult | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FoodGenerationChangeResult:
    role: str
    old_model: str | None
    new_model: str | None


@dataclass(frozen=True)
class FoodGenerationPreviewResult:
    food_id: str | None
    candidate: FoodPackageResult
    changes: tuple[FoodGenerationChangeResult, ...]
    warnings: tuple[str, ...]
    has_changes: bool


@dataclass(frozen=True)
class ElfieFoodOptionResult:
    food_id: str
    display_name: str


@dataclass(frozen=True)
class MainFoodPolicyResult:
    main_food_id: str
    effective_main_food_id: str
    main_food_options: tuple[ElfieFoodOptionResult, ...]
    main_food_unavailable: bool


@dataclass(frozen=True)
class ResolvedElfieFoodResult:
    food_id: str | None
    unavailable: bool


__all__ = tuple(
    name for name in globals() if name.endswith(("Command", "Input", "Query", "Result"))
) + ("FoodLifecycleAction",)
