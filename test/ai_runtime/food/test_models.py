from ai_runtime.food.models import (
    FIXED_FOOD_KINDS,
    ExecutionProfile,
    FoodRecipe,
    ReasoningProfile,
)


def test_fixed_food_kinds_are_stable_and_semantic():
    assert set(FIXED_FOOD_KINDS) == {
        "coarse",
        "standard",
        "focus",
        "creative",
        "tool",
        "vision",
        "premium",
        "emergency",
    }
    assert "reasoning" in FIXED_FOOD_KINDS["focus"].required_capabilities
    assert "vision" in FIXED_FOOD_KINDS["vision"].required_capabilities


def test_food_recipe_round_trip_hides_provider_details_behind_recipe():
    recipe = FoodRecipe(
        key="focus",
        display_name="清醒粮",
        description="逻辑分析",
        primary=ExecutionProfile(
            model="provider/fast-model",
            reasoning_profile=ReasoningProfile.BALANCED,
        ),
        deep=ExecutionProfile(
            model="provider/deep-model",
            reasoning_profile=ReasoningProfile.DEEP,
        ),
    )

    restored = FoodRecipe.from_dict("focus", recipe.to_dict())

    assert restored.primary.model == "provider/fast-model"
    assert restored.deep is not None
    assert restored.deep.reasoning_profile is ReasoningProfile.DEEP
