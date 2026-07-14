from runtime.food.models import (
    ExecutionProfile,
    FoodRecipe,
    FoodValidationStatus,
)
from runtime.food.planner import FoodPlanner, ModelEvidence
from runtime.food.store import FoodCatalog


def evidence():
    return [
        ModelEvidence(
            "ollama/local-small",
            frozenset({"text"}),
            True,
            cost_grade=0,
            latency_ms=100,
            local=True,
        ),
        ModelEvidence(
            "cloud/balanced",
            frozenset({"text", "reasoning"}),
            True,
            cost_grade=2,
            latency_ms=300,
        ),
        ModelEvidence(
            "cloud/tools",
            frozenset({"text"}),
            True,
            cost_grade=2,
            latency_ms=250,
            tool_test_passed=True,
        ),
        ModelEvidence(
            "cloud/vision",
            frozenset({"text", "vision"}),
            True,
            cost_grade=3,
            latency_ms=400,
        ),
        ModelEvidence(
            "cloud/deep",
            frozenset({"text", "reasoning"}),
            True,
            cost_grade=4,
            latency_ms=800,
        ),
    ]


def test_planner_generates_all_fixed_foods_from_verified_evidence():
    proposal = FoodPlanner().propose(evidence())

    assert set(proposal.catalog.recipes) == {
        "coarse",
        "standard",
        "focus",
        "creative",
        "tool",
        "vision",
        "premium",
        "emergency",
    }
    assert proposal.catalog.recipes["coarse"].primary.model == "ollama/local-small"
    assert proposal.catalog.recipes["tool"].primary.model == "cloud/tools"
    assert proposal.catalog.recipes["vision"].primary.model == "cloud/vision"
    assert proposal.catalog.recipes["premium"].primary.model == "cloud/deep"
    assert (
        proposal.catalog.recipes["standard"].validation_status
        is FoodValidationStatus.PASSED
    )


def test_emergency_food_ignores_cloud_recommendation_and_requires_local_model():
    class CloudAdvisor:
        def recommend(self, food_keys, evidence):
            return {"emergency": "cloud/deep"}

    proposal = FoodPlanner(CloudAdvisor()).propose(evidence())

    assert proposal.catalog.recipes["emergency"].primary.model == (
        "ollama/local-small"
    )


def test_emergency_food_is_unavailable_without_verified_local_model():
    cloud_only = [item for item in evidence() if not item.local]

    proposal = FoodPlanner().propose(cloud_only)

    emergency = proposal.catalog.recipes["emergency"]
    assert emergency.primary.model == ""
    assert emergency.validation_status is FoodValidationStatus.FAILED


def test_reasoning_family_display_name_enables_focus_and_premium_foods():
    custom_reasoning = ModelEvidence(
        "custom/xopglm5",
        frozenset({"text"}),
        True,
        display_name="GLM-5",
    )

    proposal = FoodPlanner().propose([custom_reasoning])

    assert proposal.catalog.recipes["focus"].primary.model == "custom/xopglm5"
    assert proposal.catalog.recipes["premium"].primary.model == "custom/xopglm5"
    assert proposal.catalog.recipes["tool"].validation_status is (
        FoodValidationStatus.FAILED
    )


def test_planner_does_not_invent_missing_vision_capability():
    no_vision = [item for item in evidence() if "vision" not in item.capabilities]

    proposal = FoodPlanner().propose(no_vision)
    vision = proposal.catalog.recipes["vision"]

    assert vision.primary.model == ""
    assert vision.validation_status is FoodValidationStatus.FAILED
    assert any("视觉粮" in warning for warning in proposal.warnings)


def test_planner_preserves_manual_recipe():
    manual = FoodRecipe(
        key="standard",
        display_name="我的标准粮",
        description="人工配置",
        primary=ExecutionProfile("cloud/manual"),
        source="manual",
    )
    current = FoodCatalog(version=3, recipes={"standard": manual})

    proposal = FoodPlanner().propose(evidence(), current)

    proposed = proposal.catalog.recipes["standard"]
    assert proposed.primary == manual.primary
    assert proposed.display_name == manual.display_name
    assert proposed.source == "manual"
    assert proposed.validation_status is FoodValidationStatus.FAILED
    standard_change = next(
        item for item in proposal.changes if item.food_key == "standard"
    )
    assert "人工管理" in standard_change.warnings[0]


class InvalidAdvisor:
    def recommend(self, food_keys, evidence):
        return {"standard": "hallucinated/model", "vision": "cloud/balanced"}


def test_planner_rejects_advisor_models_outside_verified_candidates_or_capabilities():
    proposal = FoodPlanner(InvalidAdvisor()).propose(evidence())

    assert proposal.catalog.recipes["standard"].primary.model != "hallucinated/model"
    assert proposal.catalog.recipes["vision"].primary.model == "cloud/vision"


class FailedAdvisor:
    def recommend(self, food_keys, evidence):
        raise RuntimeError("planner offline")


def test_planner_records_model_and_rule_generation_provenance():
    with_model = FoodPlanner(InvalidAdvisor()).propose(evidence())
    rules_only = FoodPlanner(FailedAdvisor()).propose(evidence())

    assert with_model.generation_sources == ("model", "rules")
    assert with_model.catalog.generation_note == "模型建议与规则校验共同生成"
    assert rules_only.generation_sources == ("rules",)
    assert rules_only.advisor_error == "planner offline"
    assert rules_only.catalog.generation_note == "规划模型不可用，使用规则生成"
