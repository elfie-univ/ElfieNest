from datetime import datetime, timezone

from ai_runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from ai_runtime.food.planner import ModelEvidence


def test_llm_advisor_is_an_optional_noop_boundary():
    advisor = LLMFoodPlanningAdvisor({}, "cloud/planner")
    result = advisor.recommend(
        ["food_common"],
        [ModelEvidence("cloud/balanced", frozenset({"text"}), True, latency_ms=200)],
    )

    assert result == {}


def test_select_planning_model_uses_first_fresh_verified_model():
    selected = select_planning_model(
        {},
        [
            ModelEvidence("cloud/stale", frozenset({"text"}), False),
            ModelEvidence(
                "cloud/reasoner",
                frozenset({"text", "reasoning"}),
                True,
                cost_grade=4,
                observed_at=datetime.now(timezone.utc).isoformat(),
            ),
        ],
    )

    assert selected == "cloud/reasoner"


def test_select_planning_model_returns_none_without_fresh_evidence():
    selected = select_planning_model(
        {},
        [ModelEvidence("ollama/gemma", frozenset({"text"}), False)],
    )

    assert selected is None
