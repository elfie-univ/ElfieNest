"""Stable model-package and routing abstractions."""

from ai_runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from ai_runtime.food.elfie_policy import (
    DEFAULT_ALLOWED_FOODS,
    ElfieFoodPolicy,
    FoodSelection,
    resolve_food_selection,
)
from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.executor import (
    FoodExecutionError,
    FoodExecutionResult,
    FoodExecutor,
    NoAvailableFoodError,
)
from ai_runtime.food.health import FoodHealth, project_food_health
from ai_runtime.food.models import (
    FIXED_FOOD_KINDS,
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FOOD_ROLES,
    FoodPackage,
    ModelAssignment,
)
from ai_runtime.food.planner import FoodPlanner, FoodUpdateProposal, ModelEvidence
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore

__all__ = [
    "FIXED_FOOD_KINDS",
    "FOOD_COMMON_ID",
    "FOOD_EMERGENCY_ID",
    "FOOD_ROLES",
    "FoodCatalog",
    "FoodCatalogStore",
    "FoodExecutionError",
    "FoodExecutionResult",
    "FoodExecutor",
    "FoodHealth",
    "FoodPackage",
    "FoodPlanner",
    "FoodUpdateProposal",
    "LLMFoodPlanningAdvisor",
    "ModelAssignment",
    "ModelEvidence",
    "ModelEvidenceStore",
    "NoAvailableFoodError",
    "project_food_health",
    "resolve_food_selection",
    "select_planning_model",
]
