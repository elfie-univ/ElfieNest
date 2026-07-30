"""Food package validation from current evidence."""

from __future__ import annotations

from collections.abc import Sequence

from ai_runtime.food.health import project_food_health
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.food.store import FoodCatalog
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite


class FoodValidationRunner:
    def validate(
        self,
        catalog: FoodCatalog,
        evidence: Sequence[ModelEvidence],
    ) -> ValidationSuite:
        evidence_by_model = {item.model: item for item in evidence}
        results = []
        for package in catalog.ordered_packages():
            health = project_food_health(package, evidence_by_model)
            passed = health.status in {"healthy", "degraded", "disabled"}
            results.append(
                CheckResult(
                    check_id=f"food.{package.key}.configuration",
                    status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                    message=f"{package.display_name}: {health.status}",
                    provider=(
                        package.primary.model.split("/", 1)[0]
                        if package.primary
                        else None
                    ),
                    model=package.primary.model if package.primary else None,
                    details={
                        "health": health.status,
                        "fallbacks": len(package.fallback),
                    },
                )
            )
        return ValidationSuite("food:catalog", tuple(results))
