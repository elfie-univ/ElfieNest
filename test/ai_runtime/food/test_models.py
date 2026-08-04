import pytest

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


def test_food_fallback_is_one_nullable_assignment_in_json():
    package = FoodPackage(
        "food_custom",
        "工作粮",
        primary=ModelAssignment("cloud/main"),
        fallback=ModelAssignment("cloud/backup"),
    )

    assert package.assignment_for("fallback") == ModelAssignment("cloud/backup")
    assert package.to_dict()["roles"]["fallback"] == {"model": "cloud/backup"}
    assert FoodPackage.from_dict("food_custom", package.to_dict()).fallback == ModelAssignment("cloud/backup")
    assert FoodPackage("food_custom", "工作粮").to_dict()["roles"]["fallback"] is None


@pytest.mark.parametrize(
    "raw_fallback",
    ["cloud/a", [], [{"model": "cloud/a"}, {"model": "cloud/b"}]],
)
def test_food_fallback_array_is_rejected_without_truncation(raw_fallback):
    with pytest.raises(ValueError, match="roles.fallback 必须是对象或 null"):
        FoodPackage.from_dict(
            "food_custom",
            {"display_name": "工作粮", "roles": {"fallback": raw_fallback}},
        )
