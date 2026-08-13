"""Food package validation from current model evidence."""

from __future__ import annotations

from collections.abc import Sequence

from app.features.configuration.food import StoredModelEvidence, project_food_health
from elfie.brain.reasoning.food_port import FoodCatalog
from infrastructure.models.food_technology import stored_food_package
from infrastructure.models.validation.validation_models import (
    CheckResult,
    CheckStatus,
    ValidationSuite,
)


class FoodValidationRunner:
    def validate(
        self,
        catalog: FoodCatalog,
        evidence: Sequence[StoredModelEvidence],
    ) -> ValidationSuite:
        evidence_by_model = {item.reference: item for item in evidence}
        results = []
        for package in catalog.ordered_packages():
            health = project_food_health(
                stored_food_package(package),
                evidence_by_model,
            )
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
                        "fallback_configured": package.fallback is not None,
                    },
                )
            )
        return ValidationSuite("food:catalog", tuple(results))
