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
        vision=ExecutionProfile(model="provider/vision-model"),
        local_only=False,
    )

    restored = FoodRecipe.from_dict("focus", recipe.to_dict())

    assert restored.primary.model == "provider/fast-model"
    assert restored.deep is not None
    assert restored.deep.reasoning_profile is ReasoningProfile.DEEP
    assert restored.vision is not None
    assert restored.vision.model == "provider/vision-model"


def test_food_recipe_does_not_persist_tool_permissions():
    recipe = FoodRecipe(
        key="food_00000001",
        display_name="日常粮",
        description="",
        primary=ExecutionProfile(
            model="provider/model",
            tools=("web_search", "local_file"),
        ),
    )

    payload = recipe.to_dict()
    restored = FoodRecipe.from_dict(recipe.key, payload)

    assert "tools" not in payload["primary"]
    assert restored.primary.tools == ()
