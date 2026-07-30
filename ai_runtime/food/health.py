"""Read-time locality and health projections for food packages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ai_runtime.food.models import FoodPackage
from ai_runtime.food.planner import ModelEvidence


@dataclass(frozen=True)
class FoodHealth:
    status: str
    locality: str
    latest_evidence_at: str | None


def project_food_health(
    package: FoodPackage,
    evidence: Mapping[str, ModelEvidence],
) -> FoodHealth:
    if package.archived:
        return FoodHealth("archived", _locality(package, evidence), None)
    if not package.enabled:
        return FoodHealth("disabled", _locality(package, evidence), None)
    if package.primary is None:
        return FoodHealth("unconfigured", _locality(package, evidence), None)
    referenced = [evidence.get(item) for item in package.model_references]
    primary = evidence.get(package.primary.model)
    latest = max(
        (item.observed_at for item in referenced if item and item.observed_at),
        default=None,
    )
    if primary is None or not primary.is_fresh():
        fallback_works = any(
            item is not None and item.is_fresh()
            for item in (evidence.get(value.model) for value in package.fallback)
        )
        return FoodHealth(
            "degraded" if fallback_works else "unavailable",
            _locality(package, evidence),
            latest,
        )
    optional_failed = any(item is None or not item.is_fresh() for item in referenced[1:])
    return FoodHealth(
        "degraded" if optional_failed else "healthy",
        _locality(package, evidence),
        latest,
    )


def _locality(
    package: FoodPackage,
    evidence: Mapping[str, ModelEvidence],
) -> str:
    values = {
        item.local
        for reference in package.model_references
        if (item := evidence.get(reference)) is not None
    }
    if not values:
        return "unknown"
    if values == {True}:
        return "local"
    if values == {False}:
        return "remote"
    return "mixed"
