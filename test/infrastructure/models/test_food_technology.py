from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.features.configuration.food import (
    StoredFoodChange,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredFoodProposal,
    StoredModelEvidence,
)
from infrastructure.models.food_technology import ModelFoodTechnologyAdapter


def test_adapter_delegates_evidence_health_and_planning_to_owned_rules(
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    evidence = StoredModelEvidence(
        reference="cloud/main",
        display_name="Main",
        capabilities=frozenset({"text"}),
        verified=True,
        observed_at=now,
        fresh=True,
    )

    class Evidence:
        def list_model_evidence(self):
            return (evidence,)

        def validate_package(self, package):
            validated.append(package)

    validated: list[StoredFoodPackage] = []
    monkeypatch.setattr(
        "infrastructure.models.food_technology.project_food_health",
        lambda package, items: StoredFoodHealth("healthy", "remote", now),
    )

    class Planner:
        def propose_package(self, package, items, **options):
            _ = items, options
            proposed = replace(package, enabled=True, primary_model="cloud/main")
            return StoredFoodProposal(
                proposed,
                (StoredFoodChange("primary", None, "cloud/main"),),
                (),
            )

    monkeypatch.setattr("infrastructure.models.food_technology.FoodPlanner", Planner)
    adapter = ModelFoodTechnologyAdapter(Evidence())
    package = StoredFoodPackage("food_custom", "Custom")
    defaults = adapter.food_defaults()
    stored_evidence = adapter.list_model_evidence()

    adapter.validate_package(package)
    health = adapter.project_health(package, stored_evidence)
    proposal = adapter.propose_package(
        package,
        stored_evidence,
        connection_ids=("cloud",),
        local_first=False,
        allow_remote=True,
    )

    assert stored_evidence[0].fresh is True
    assert defaults.default_food_id == "food_common"
    assert health.status == "healthy"
    assert proposal.package.primary_model == "cloud/main"
    assert validated[0].food_id == "food_custom"
