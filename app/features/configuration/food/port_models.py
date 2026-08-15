"""Strict models crossing Food-owned technical Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FoodSystemRole = Literal["emergency", "common"]
FoodVisibilityMode = Literal["global", "users"]

FOOD_ROLES = ("primary", "reasoning", "vision", "tool", "fallback")


@dataclass(frozen=True)
class StoredFoodDefaults:
    catalog_version: int
    default_food_id: str
    emergency_food_id: str
    system_food_ids: frozenset[str]


@dataclass(frozen=True)
class StoredFoodPackage:
    food_id: str
    display_name: str
    system_role: FoodSystemRole | None = None
    enabled: bool = True
    archived: bool = False
    primary_model: str | None = None
    reasoning_model: str | None = None
    vision_model: str | None = None
    tool_model: str | None = None
    fallback_model: str | None = None
    visibility_mode: FoodVisibilityMode = "global"
    visible_user_ids: tuple[int, ...] = ()
    # Product policy can require an optional role without making it a
    # permanently scheduled probe for every Food.  Persistence may omit this
    # empty default until the policy is explicitly exposed.
    required_roles: frozenset[str] = frozenset()

    @property
    def model_references(self) -> tuple[str, ...]:
        return tuple(
            reference
            for reference in (
                self.primary_model,
                self.reasoning_model,
                self.vision_model,
                self.tool_model,
                self.fallback_model,
            )
            if reference is not None
        )

    def model_for_role(self, role: str) -> str | None:
        values = {
            "primary": self.primary_model,
            "reasoning": self.reasoning_model,
            "vision": self.vision_model,
            "tool": self.tool_model,
            "fallback": self.fallback_model,
        }
        if role not in values:
            raise ValueError(f"unknown Food role: {role}")
        return values[role]


@dataclass(frozen=True)
class StoredModelEvidence:
    reference: str
    display_name: str
    capabilities: frozenset[str]
    verified: bool
    cost_grade: int = 2
    latency_ms: float | None = None
    tool_test_passed: bool = False
    local: bool = False
    observed_at: str = ""
    status: str = "never_verified"
    fresh: bool = False


@dataclass(frozen=True)
class StoredFoodHealth:
    status: str
    locality: str
    latest_evidence_at: str | None


@dataclass(frozen=True)
class StoredFoodChange:
    role: str
    old_model: str | None
    new_model: str | None


@dataclass(frozen=True)
class StoredFoodProposal:
    package: StoredFoodPackage
    changes: tuple[StoredFoodChange, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class StoredElfieFoodAssignment:
    elfie_id: str
    owner_user_id: int
    main_food_id: str | None


__all__ = (
    "FOOD_ROLES",
    "FoodSystemRole",
    "FoodVisibilityMode",
    "StoredElfieFoodAssignment",
    "StoredFoodChange",
    "StoredFoodDefaults",
    "StoredFoodHealth",
    "StoredFoodPackage",
    "StoredFoodProposal",
    "StoredModelEvidence",
)
