from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ai_runtime.food.health import FoodHealth
from ai_runtime.food.models import FoodPackage, ModelAssignment
from ai_runtime.food.planner import FoodChange, FoodUpdateProposal, ModelEvidence
from app.features.configuration.food import StoredFoodPackage
from infrastructure.models.food_technology import RuntimeFoodTechnologyAdapter


def test_adapter_delegates_evidence_health_and_planning_to_single_runtime_algorithms(
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    evidence = ModelEvidence(
        model="cloud/main",
        display_name="Main",
        capabilities=frozenset({"text"}),
        verified=True,
        observed_at=now,
    )
    monkeypatch.setattr(
        "infrastructure.models.food_technology.query_model_evidence",
        lambda: {evidence.model: evidence},
    )
    monkeypatch.setattr(
        "infrastructure.models.food_technology.project_food_health",
        lambda package, items: FoodHealth("healthy", "remote", now),
    )
    validated: list[FoodPackage] = []
    monkeypatch.setattr(
        "infrastructure.models.food_technology.validate_food_catalog_model_references",
        lambda catalog: validated.extend(catalog.packages.values()),
    )

    @dataclass
    class Planner:
        def propose_package(self, package, items, **options):
            _ = items, options
            proposed = FoodPackage(
                key=package.key,
                display_name=package.display_name,
                enabled=True,
                primary=ModelAssignment("cloud/main"),
            )
            return FoodUpdateProposal(
                proposed,
                (FoodChange("primary", None, "cloud/main"),),
            )

    monkeypatch.setattr("infrastructure.models.food_technology.FoodPlanner", Planner)
    adapter = RuntimeFoodTechnologyAdapter()
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
    assert validated[0].key == "food_custom"
