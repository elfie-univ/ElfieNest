from ai_runtime.food.models import FoodPackage
from ai_runtime.food.store import FoodCatalog
from ai_runtime.validation.foods import FoodValidationRunner


def test_unconfigured_system_food_is_reported_without_inventing_model():
    suite = FoodValidationRunner().validate(
        FoodCatalog(packages={"food_x": FoodPackage("food_x", "X")}),
        [],
    )
    assert not suite.passed
    assert suite.results[0].model is None
