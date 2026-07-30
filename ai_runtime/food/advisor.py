"""Optional advisor boundary; deterministic rules remain authoritative."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ai_runtime.food.planner import ModelEvidence


class LLMFoodPlanningAdvisor:
    def __init__(self, config: Any, planning_model: str) -> None:
        self.config = config
        self.planning_model = planning_model

    def recommend(
        self,
        food_keys: Sequence[str],
        evidence: Sequence[ModelEvidence],
    ) -> Mapping[str, str]:
        _ = food_keys, evidence
        return {}


def select_planning_model(config: Any, evidence: Sequence[ModelEvidence]) -> str | None:
    _ = config
    return next((item.model for item in evidence if item.is_fresh()), None)
