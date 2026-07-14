from runtime.food.elfie_policy import (
    DEFAULT_ALLOWED_FOODS,
    ElfieFoodPolicy,
    load_elfie_food_policy,
    resolve_food_selection,
    save_elfie_food_policy,
)
from runtime.food.models import ExecutionProfile, FoodRecipe, FoodValidationStatus
from runtime.food.store import FoodCatalog


def catalog():
    return FoodCatalog(
        recipes={
            "coarse": FoodRecipe(
                "coarse",
                "粗粮",
                "本地",
                ExecutionProfile("ollama/local"),
            ),
            "standard": FoodRecipe(
                "standard",
                "标准粮",
                "默认",
                ExecutionProfile("cloud/standard"),
            ),
            "focus": FoodRecipe(
                "focus",
                "清醒粮",
                "深度推理",
                ExecutionProfile("cloud/focus"),
            ),
            "premium": FoodRecipe(
                "premium",
                "精粮",
                "高级",
                ExecutionProfile(""),
                validation_status=FoodValidationStatus.FAILED,
            ),
        }
    )


def test_food_policy_round_trip(tmp_path):
    policy = ElfieFoodPolicy(
        "elfie-1", "standard", ("coarse", "standard", "focus"), "coarse"
    )

    save_elfie_food_policy(policy, tmp_path)

    assert load_elfie_food_policy("elfie-1", tmp_path) == policy


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
