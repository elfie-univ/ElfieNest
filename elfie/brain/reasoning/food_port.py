"""Read-only Food boundary and selection rules owned by one Elfie's brain."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

FOOD_EMERGENCY_ID = "food_emergency"
FOOD_COMMON_ID = "food_common"
SYSTEM_FOOD_IDS = frozenset({FOOD_EMERGENCY_ID, FOOD_COMMON_ID})
FOOD_ROLES = ("primary", "reasoning", "vision", "tool", "fallback")


@dataclass(frozen=True)
class FoodAssignment:
    """One exact provider connection and model reference."""

    model: str


@dataclass(frozen=True)
class FoodPackage:
    """Immutable Food projection needed by model execution."""

    key: str
    display_name: str
    system_role: str | None = None
    enabled: bool = True
    archived: bool = False
    primary: FoodAssignment | None = None
    reasoning: FoodAssignment | None = None
    vision: FoodAssignment | None = None
    tool: FoodAssignment | None = None
    fallback: FoodAssignment | None = None

    @property
    def model_references(self) -> tuple[str, ...]:
        assignments = (
            self.primary,
            self.reasoning,
            self.vision,
            self.tool,
            self.fallback,
        )
        return tuple(item.model for item in assignments if item is not None)

    def assignment_for(self, role: str) -> FoodAssignment | None:
        assignments = {
            "primary": self.primary,
            "reasoning": self.reasoning,
            "vision": self.vision,
            "tool": self.tool,
            "fallback": self.fallback,
        }
        if role not in assignments:
            raise ValueError(f"unknown Food role: {role}")
        return assignments[role]


def system_food_packages() -> dict[str, FoodPackage]:
    """Return the two disabled system projections used by isolated runtimes."""
    return {
        FOOD_EMERGENCY_ID: FoodPackage(
            key=FOOD_EMERGENCY_ID,
            display_name="保底粮",
            system_role="emergency",
            enabled=False,
        ),
        FOOD_COMMON_ID: FoodPackage(
            key=FOOD_COMMON_ID,
            display_name="常用粮",
            system_role="common",
            enabled=False,
        ),
    }


@dataclass(frozen=True)
class FoodCatalog:
    """Read-only catalog snapshot returned by the Food Port."""

    version: int = 1
    global_default_food_id: str = FOOD_COMMON_ID
    global_emergency_food_id: str = FOOD_EMERGENCY_ID
    packages: Mapping[str, FoodPackage] = field(default_factory=system_food_packages)

    def ordered_packages(self) -> tuple[FoodPackage, ...]:
        ordered = [
            self.packages[food_id]
            for food_id in (self.global_emergency_food_id, self.global_default_food_id)
            if food_id in self.packages
        ]
        ordered.extend(
            package
            for key, package in self.packages.items()
            if key not in {self.global_emergency_food_id, self.global_default_food_id}
        )
        return tuple(ordered)


class FoodPort(Protocol):
    """Technical reader that supplies the current Food catalog projection."""

    def load(self) -> FoodCatalog:
        """Load the complete immutable Food projection."""
        ...


@dataclass(frozen=True)
class MainFoodSelection:
    """Persisted main Food ID plus its authorization/health outcome."""

    food_id: str | None
    unavailable: bool = False


@dataclass(frozen=True)
class MainFoodRoute:
    """The one package eligible for role and same-Food fallback execution."""

    food_id: str
    used_emergency: bool


class NoAvailableFoodError(RuntimeError):
    """No selected/default or emergency Food can execute the request."""

    code = "no_available_food"

    def __init__(
        self,
        message: str = "no_available_food",
        attempts: tuple[dict[str, str], ...] = (),
    ) -> None:
        super().__init__(message)
        self.attempts = attempts


def resolve_main_food(
    catalog: FoodCatalog,
    selection: MainFoodSelection,
    *,
    is_usable: Callable[[FoodPackage], bool],
) -> MainFoodRoute:
    """Choose selected/default Food, then the global emergency Food once."""
    emergency_id = catalog.global_emergency_food_id
    if selection.unavailable:
        emergency = catalog.packages.get(emergency_id)
        if emergency is not None and is_usable(emergency):
            return MainFoodRoute(emergency_id, used_emergency=True)
        raise NoAvailableFoodError("no_available_food")

    primary_id = selection.food_id or catalog.global_default_food_id
    primary = catalog.packages.get(primary_id)
    if primary is not None and is_usable(primary):
        return MainFoodRoute(primary_id, used_emergency=False)
    emergency = catalog.packages.get(emergency_id)
    if emergency is not None and is_usable(emergency):
        return MainFoodRoute(emergency_id, used_emergency=True)
    raise NoAvailableFoodError("no_available_food")


def is_food_executable(
    package: FoodPackage,
    *,
    is_model_available: Callable[[str], bool],
) -> bool:
    """Return whether the package can execute through its primary or fallback."""
    if not package.enabled or package.archived or package.primary is None:
        return False
    candidates = (package.primary, package.fallback)
    return any(
        assignment is not None and is_model_available(assignment.model)
        for assignment in candidates
    )


__all__ = (
    "FOOD_COMMON_ID",
    "FOOD_EMERGENCY_ID",
    "FOOD_ROLES",
    "SYSTEM_FOOD_IDS",
    "FoodAssignment",
    "FoodCatalog",
    "FoodPackage",
    "FoodPort",
    "MainFoodRoute",
    "MainFoodSelection",
    "NoAvailableFoodError",
    "resolve_main_food",
    "is_food_executable",
    "system_food_packages",
)
