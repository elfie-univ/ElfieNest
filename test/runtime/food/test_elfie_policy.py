from runtime.food.elfie_policy import (
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


def test_unauthorized_food_is_clamped_to_default():
    policy = ElfieFoodPolicy("elfie-1", "standard", ("coarse", "standard"), "coarse")

    selection = resolve_food_selection(policy, "premium", catalog())

    assert selection.actual_food == "standard"
    assert selection.clamped is True
    assert selection.reason == "food_not_allowed"


def test_unavailable_allowed_food_uses_configured_fallback():
    policy = ElfieFoodPolicy(
        "elfie-1", "standard", ("coarse", "standard", "premium"), "coarse"
    )

    selection = resolve_food_selection(policy, "premium", catalog())

    assert selection.actual_food == "coarse"
    assert selection.reason == "requested_food_unavailable"
