import pytest

from elfie.brain.food_port import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodAssignment,
    FoodCatalog,
    FoodPackage,
    MainFoodSelection,
    NoAvailableFoodError,
    is_food_executable,
    resolve_main_food,
)


def _catalog() -> FoodCatalog:
    return FoodCatalog(
        packages={
            FOOD_EMERGENCY_ID: FoodPackage(
                key=FOOD_EMERGENCY_ID,
                display_name="保底粮",
                system_role="emergency",
                primary=FoodAssignment("local/emergency"),
            ),
            FOOD_COMMON_ID: FoodPackage(
                key=FOOD_COMMON_ID,
                display_name="常用粮",
                system_role="common",
                primary=FoodAssignment("local/common"),
            ),
            "food_custom": FoodPackage(
                key="food_custom",
                display_name="自定义粮",
                primary=FoodAssignment("cloud/custom"),
            ),
        }
    )


def test_catalog_orders_system_foods_before_custom_foods() -> None:
    assert [item.key for item in _catalog().ordered_packages()] == [
        FOOD_EMERGENCY_ID,
        FOOD_COMMON_ID,
        "food_custom",
    ]


def test_resolver_uses_selected_then_default_then_emergency() -> None:
    catalog = _catalog()

    selected = resolve_main_food(
        catalog,
        MainFoodSelection("food_custom"),
        is_usable=lambda package: package.key != FOOD_EMERGENCY_ID,
    )
    default = resolve_main_food(
        catalog,
        MainFoodSelection(None),
        is_usable=lambda package: package.key != FOOD_EMERGENCY_ID,
    )
    emergency = resolve_main_food(
        catalog,
        MainFoodSelection("food_custom", unavailable=True),
        is_usable=lambda package: package.key == FOOD_EMERGENCY_ID,
    )

    assert selected.food_id == "food_custom" and not selected.used_emergency
    assert default.food_id == FOOD_COMMON_ID and not default.used_emergency
    assert emergency.food_id == FOOD_EMERGENCY_ID and emergency.used_emergency


def test_resolver_raises_typed_error_when_no_food_is_usable() -> None:
    with pytest.raises(NoAvailableFoodError) as error:
        resolve_main_food(
            _catalog(),
            MainFoodSelection("food_custom", unavailable=True),
            is_usable=lambda package: False,
        )

    assert error.value.code == "no_available_food"


def test_executable_food_requires_primary_and_available_primary_or_fallback() -> None:
    package = FoodPackage(
        key="food_custom",
        display_name="Custom",
        primary=FoodAssignment("cloud/main"),
        fallback=FoodAssignment("local/backup"),
    )

    assert is_food_executable(
        package,
        is_model_available=lambda model: model == "local/backup",
    )
    assert not is_food_executable(
        package,
        is_model_available=lambda model: False,
    )
