from ai_runtime.food.elfie_policy import (
    DEFAULT_ALLOWED_FOODS,
    ElfieFoodPolicy,
    resolve_food_selection,
)
from ai_runtime.food.models import FoodPackage, ModelAssignment
from ai_runtime.food.store import FoodCatalog


def catalog():
    return FoodCatalog(
        packages={
            "coarse": FoodPackage(
                key="coarse",
                display_name="粗粮",
                primary=ModelAssignment(model="ollama/local"),
            ),
            "standard": FoodPackage(
                key="standard",
                display_name="标准粮",
                primary=ModelAssignment(model="cloud/standard"),
            ),
            "focus": FoodPackage(
                key="focus",
                display_name="清醒粮",
                primary=ModelAssignment(model="cloud/focus"),
            ),
            "premium": FoodPackage(
                key="premium",
                display_name="精粮",
                primary=ModelAssignment(model=""),
                enabled=False,
            ),
        }
    )


def test_food_policy_mapping_round_trip():
    policy = ElfieFoodPolicy(
        "elfie-1", "standard", ("coarse", "standard", "focus"), "coarse"
    )

    assert ElfieFoodPolicy.from_dict("elfie-1", policy.to_dict()) == policy


def test_unauthorized_premium_is_clamped_to_strongest_allowed_reasoning_food():
    policy = ElfieFoodPolicy(
        "elfie-1", "standard", ("coarse", "standard", "focus"), "coarse"
    )

    selection = resolve_food_selection(policy, "premium", catalog())

    assert selection.actual_food == "focus"
    assert selection.clamped is True
    assert selection.reason == "food_not_allowed"


def test_unavailable_allowed_food_uses_configured_fallback():
    policy = ElfieFoodPolicy(
        "elfie-1", "standard", ("coarse", "standard", "premium"), "coarse"
    )

    selection = resolve_food_selection(policy, "premium", catalog())

    assert selection.actual_food == "coarse"
    assert selection.reason == "requested_food_unavailable"


def test_default_policy_allows_capability_foods_but_requires_premium_opt_in():
    policy = ElfieFoodPolicy("elfie-1")

    assert policy.allowed_foods == DEFAULT_ALLOWED_FOODS
    assert {"tool", "vision", "emergency"} <= set(policy.allowed_foods)
    assert "premium" not in policy.allowed_foods
