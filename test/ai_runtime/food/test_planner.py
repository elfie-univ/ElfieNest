from datetime import datetime, timedelta, timezone

from ai_runtime.food.models import FoodPackage
from ai_runtime.food.planner import FoodPlanner, ModelEvidence


def _evidence(model, *, local=False, age=0, capabilities=("text",)):
    return ModelEvidence(
        model=model,
        capabilities=frozenset(capabilities),
        verified=True,
        local=local,
        tool_test_passed="tools" in capabilities,
        observed_at=(datetime.now(timezone.utc) - timedelta(hours=age)).isoformat(),
    )


def test_planner_uses_only_fresh_scoped_models_and_local_first():
    proposal = FoodPlanner().propose_package(
        FoodPackage("food_emergency", "保底", system_role="emergency"),
        [
            _evidence("cloud_0001/fast"),
            _evidence("ollama_0001/local", local=True),
            _evidence("ollama_0001/stale", local=True, age=48),
        ],
        connection_ids=["ollama_0001", "cloud_0001"],
        local_first=True,
    )
    assert proposal.package.primary.model == "ollama_0001/local"
    assert proposal.package.fallback is not None
    assert "stale" not in str(proposal.package.to_dict())
