from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodPackage,
)
from ai_runtime.food.store import FoodCatalog, fingerprint_source


def test_food_catalog_projection_orders_system_packages_before_custom_rows() -> None:
    custom = FoodPackage("food_custom", "自定义粮", enabled=False)
    catalog = FoodCatalog(
        packages={
            custom.key: custom,
            **FoodCatalog().packages,
        }
    )

    assert [item.key for item in catalog.ordered_packages()] == [
        FOOD_EMERGENCY_ID,
        FOOD_COMMON_ID,
        "food_custom",
    ]


def test_food_catalog_projection_serializes_visibility_without_file_storage() -> None:
    package = FoodPackage(
        "food_private",
        "指定用户粮",
        enabled=False,
        visibility_mode="users",
        visible_user_ids=(5, 2, 5),
    )

    payload = FoodCatalog(packages={package.key: package}).to_dict()

    assert payload["packages"]["food_private"]["visibility_mode"] == "users"
    assert payload["packages"]["food_private"]["visible_user_ids"] == [2, 5]


def test_fingerprint_source_is_stable_for_mapping_order() -> None:
    assert fingerprint_source({"b": 2, "a": 1}) == fingerprint_source(
        {"a": 1, "b": 2}
    )
