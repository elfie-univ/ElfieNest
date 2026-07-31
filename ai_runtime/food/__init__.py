"""Stable model-package and routing abstractions."""

from ai_runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from ai_runtime.food.evidence import query_model_evidence, record_model_evidence
from ai_runtime.food.executor import (
    FoodExecutionError,
    FoodExecutionResult,
    FoodExecutor,
    NoAvailableFoodError,
)
from ai_runtime.food.health import FoodHealth, project_food_health
from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FOOD_ROLES,
    FoodPackage,
    ModelAssignment,
)
from ai_runtime.food.planner import FoodPlanner, FoodUpdateProposal, ModelEvidence
from ai_runtime.food.resolver import MainFoodRoute, MainFoodSelection, resolve_main_food
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore

__all__ = [
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
    "MainFoodRoute",
    "MainFoodSelection",
    "NoAvailableFoodError",
    "project_food_health",
    "query_model_evidence",
    "record_model_evidence",
    "resolve_main_food",
    "select_planning_model",
]
