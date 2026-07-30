from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodPackage,
    ModelAssignment,
    system_food_packages,
)


def test_clean_catalog_has_exactly_two_ordered_system_packages():
    packages = system_food_packages()
    assert list(packages) == [FOOD_EMERGENCY_ID, FOOD_COMMON_ID]
    assert all(not package.enabled for package in packages.values())


def test_food_serialization_contains_only_role_references_and_lifecycle():
    package = FoodPackage(
        "food_custom",
        "工作粮",
        primary=ModelAssignment("openai_api_0001/gpt"),
    )
    payload = package.to_dict()
    assert payload["roles"]["primary"] == {"model": "openai_api_0001/gpt"}
    serialized = str(payload)
    assert "max_tokens" not in serialized
    assert "tools_permissions" not in serialized
