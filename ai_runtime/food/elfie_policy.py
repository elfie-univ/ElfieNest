"""每个精灵的粮食选择边界。

情绪与认知如何选择粮食由 ``elfie`` 上层实现；本模块只保存默认粮食、允许
范围和不可用时的降级粮食，并保证请求不会越权。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.executor import NoAvailableFoodError
from ai_runtime.food.models import FIXED_FOOD_KINDS
from ai_runtime.food.store import FoodCatalog

DEFAULT_ALLOWED_FOODS: tuple[str, ...] = (
    "coarse",
    "standard",
    "focus",
    "creative",
    "tool",
    "vision",
    "emergency",
)

# 只用于“认知升级被权限上限截断”时寻找最强可用档。
# 工具、视觉和紧急粮是能力类型，不参与这个强弱排序。
REASONING_FOOD_ORDER: tuple[str, ...] = (
    "coarse",
    "standard",
    "focus",
    "premium",
)


@dataclass(frozen=True)
class ElfieFoodPolicy:
    elfie_id: str
    default_food: str = "standard"
    allowed_foods: tuple[str, ...] = DEFAULT_ALLOWED_FOODS
    fallback_food: str = "coarse"

    def to_dict(self) -> dict[str, Any]:
        return {
            "elfie_id": self.elfie_id,
            "default_food": self.default_food,
            "allowed_foods": list(self.allowed_foods),
            "fallback_food": self.fallback_food,
        }

    @classmethod
    def from_dict(cls, elfie_id: str, data: Mapping[str, Any]) -> ElfieFoodPolicy:
        allowed = tuple(
            str(item)
            for item in data.get("allowed_foods", DEFAULT_ALLOWED_FOODS)
            if str(item) in FIXED_FOOD_KINDS
        )
        if not allowed:
            allowed = DEFAULT_ALLOWED_FOODS
        default_food = str(data.get("default_food", "standard"))
        fallback_food = str(data.get("fallback_food", "coarse"))
        return cls(
            elfie_id=elfie_id,
            default_food=default_food if default_food in allowed else allowed[0],
            allowed_foods=allowed,
            fallback_food=fallback_food if fallback_food in allowed else allowed[0],
        )


@dataclass(frozen=True)
class FoodSelection:
    requested_food: str
    actual_food: str
    clamped: bool
    reason: str


def resolve_food_selection(
    policy: ElfieFoodPolicy,
    requested_food: str | None,
    catalog: FoodCatalog,
) -> FoodSelection:
    requested = requested_food or policy.default_food
    if requested not in policy.allowed_foods:
        if requested in {"focus", "premium"}:
            authorized_reasoning = tuple(
                food_key
                for food_key in reversed(REASONING_FOOD_ORDER)
                if food_key in policy.allowed_foods
            )
            candidates = (
                *authorized_reasoning,
                policy.default_food,
                policy.fallback_food,
                *policy.allowed_foods,
            )
        else:
            candidates = (
                policy.default_food,
                policy.fallback_food,
                *policy.allowed_foods,
            )
        actual = _first_available(candidates, catalog)
        return FoodSelection(
            requested_food=requested,
            actual_food=actual,
            clamped=True,
            reason="food_not_allowed",
        )
    if _food_available(requested, catalog):
        return FoodSelection(requested, requested, False, "requested_food_available")
    actual = _first_available(
        (policy.fallback_food, policy.default_food, *policy.allowed_foods), catalog
    )
    return FoodSelection(
        requested_food=requested,
        actual_food=actual,
        clamped=actual != requested,
        reason="requested_food_unavailable",
    )


def _food_available(food_key: str, catalog: FoodCatalog) -> bool:
    recipe = catalog.recipes.get(food_key)
    if not recipe or not recipe.enabled or recipe.archived or not recipe.primary or not recipe.primary.model:
        return False
    try:
        from ai_runtime.gateway.agent import RuntimeAgent
        provider = RuntimeAgent._provider_for_model(recipe.primary.model)
        config = LLMRuntimeConfig.load()
        return provider in config.providers
    except Exception:
        return False


def _first_available(candidates: tuple[str, ...], catalog: FoodCatalog) -> str:
    for food_key in candidates:
        if _food_available(food_key, catalog):
            return food_key
    return candidates[0] if candidates else "coarse"
