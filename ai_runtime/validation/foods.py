"""粮食配方层验证。"""

from __future__ import annotations

from collections.abc import Sequence

from ai_runtime.food.models import FIXED_FOOD_KINDS
from ai_runtime.food.planner import ModelEvidence, validate_food_recipe
from ai_runtime.food.store import FoodCatalog
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite


class FoodValidationRunner:
    """验证固定粮食是否能由已验证模型证据完整支撑。"""

    def validate(
        self,
        catalog: FoodCatalog,
        evidence: Sequence[ModelEvidence],
    ) -> ValidationSuite:
        results: list[CheckResult] = []
        for food_key, kind in FIXED_FOOD_KINDS.items():
            recipe = catalog.recipes.get(food_key)
            if recipe is None:
                results.append(
                    CheckResult(
                        check_id=f"food.{food_key}.configuration",
                        status=CheckStatus.FAILED,
                        message="粮食尚未生成",
                    )
                )
                continue
            warnings = validate_food_recipe(recipe, evidence)
            # validation_status 是上次生成时的快照，不能覆盖本次实时验证结果。
            passed = not warnings
            results.append(
                CheckResult(
                    check_id=f"food.{food_key}.configuration",
                    status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                    message=(
                        f"{kind.display_name}配方验证通过"
                        if passed
                        else "; ".join(warnings) or "配方被标记为不可用"
                    ),
                    provider=(
                        recipe.primary.model.split("/", 1)[0]
                        if "/" in recipe.primary.model
                        else "ollama"
                    ),
                    model=recipe.primary.model,
                    details={
                        "reasoning_profile": recipe.primary.reasoning_profile.value,
                        "technical_fallbacks": len(recipe.technical_fallbacks),
                        "provider_options_configured": bool(
                            recipe.primary.provider_options
                        ),
                    },
                )
            )
        return ValidationSuite("food:catalog", tuple(results))
