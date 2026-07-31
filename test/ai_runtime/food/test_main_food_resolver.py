import pytest

from ai_runtime.food.executor import NoAvailableFoodError
from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodPackage,
    ModelAssignment,
)
from ai_runtime.food.resolver import MainFoodSelection, resolve_main_food
from ai_runtime.food.store import FoodCatalog


def _catalog() -> FoodCatalog:
    return FoodCatalog(
        packages={
            FOOD_EMERGENCY_ID: FoodPackage(
                key=FOOD_EMERGENCY_ID,
                display_name="保底粮",
                system_role="emergency",
                primary=ModelAssignment("local/emergency"),
            ),
            FOOD_COMMON_ID: FoodPackage(
                key=FOOD_COMMON_ID,
                display_name="常用粮",
                system_role="common",
                primary=ModelAssignment("local/common"),
            ),
            "food_custom": FoodPackage(
                key="food_custom",
                display_name="自定义粮",
                primary=ModelAssignment("cloud/custom"),
            ),
        }
    )


def test_resolver_uses_configured_main_food_when_it_is_usable() -> None:
    # Given: a visible healthy custom main food.
    catalog = _catalog()

    # When: the Elfie requests a semantic role.
    route = resolve_main_food(
        catalog,
        MainFoodSelection("food_custom"),
        is_usable=lambda package: package.key != FOOD_EMERGENCY_ID,
    )

    # Then: the resolver preserves that one selected food.
    assert route.food_id == "food_custom"
    assert route.used_emergency is False


def test_resolver_uses_common_only_when_no_main_food_is_configured() -> None:
    # Given: an Elfie without an explicit main-food assignment.
    catalog = _catalog()

    # When: it needs a model.
    route = resolve_main_food(
        catalog,
        MainFoodSelection(None),
        is_usable=lambda package: package.key != FOOD_EMERGENCY_ID,
    )

    # Then: the common system food is the default.
    assert route.food_id == FOOD_COMMON_ID


def test_resolver_uses_emergency_when_explicit_main_food_is_unavailable() -> None:
    # Given: an explicit main food that lost authorization or health.
    catalog = _catalog()

    # When: the resolver receives the unavailable selection.
    route = resolve_main_food(
        catalog,
        MainFoodSelection("food_custom", unavailable=True),
        is_usable=lambda package: package.key in {FOOD_COMMON_ID, FOOD_EMERGENCY_ID},
    )

    # Then: it attempts the global emergency food once, not another custom food.
    assert route.food_id == FOOD_EMERGENCY_ID
    assert route.used_emergency is True


def test_resolver_raises_typed_error_when_no_food_is_usable() -> None:
    # Given: no usable main or emergency food.
    catalog = _catalog()

    # When/Then: resolution has a typed terminal failure.
    with pytest.raises(NoAvailableFoodError) as error:
        resolve_main_food(
            catalog,
            MainFoodSelection("food_custom", unavailable=True),
            is_usable=lambda package: False,
        )
    assert error.value.code == "no_available_food"
