from ai_runtime.food.models import ExecutionProfile, FoodRecipe, FoodValidationStatus
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.food.store import FoodCatalog
from ai_runtime.validation.foods import FoodValidationRunner
from ai_runtime.validation.models import CheckStatus


def test_food_validation_reports_missing_and_supported_recipes():
    catalog = FoodCatalog(
        recipes={
            "standard": FoodRecipe(
                "standard",
                "标准粮",
                "默认",
                ExecutionProfile("ollama/local"),
                validation_status=FoodValidationStatus.PASSED,
            )
        }
    )
    evidence = [ModelEvidence("ollama/local", frozenset({"text"}), True, local=True)]

    suite = FoodValidationRunner().validate(catalog, evidence)

    standard = next(
        result
        for result in suite.results
        if result.check_id.startswith("food.standard")
    )
    vision = next(
        result for result in suite.results if result.check_id.startswith("food.vision")
    )
    assert standard.status is CheckStatus.PASSED
    assert vision.status is CheckStatus.FAILED
    assert suite.passed is False


def test_food_validation_distinguishes_empty_unverified_and_real_failure():
    recipes = {
        "focus": FoodRecipe("focus", "专注粮", "", ExecutionProfile("")),
        "standard": FoodRecipe(
            "standard", "标准粮", "", ExecutionProfile("cloud/missing")
        ),
        "creative": FoodRecipe(
            "creative", "灵感粮", "", ExecutionProfile("cloud/failed")
        ),
    }
    suite = FoodValidationRunner().validate(
        FoodCatalog(recipes=recipes),
        [ModelEvidence("cloud/failed", frozenset({"text"}), False)],
    )
    by_id = {result.check_id: result for result in suite.results}

    assert "未配置主模型" in by_id["food.focus.configuration"].message
    assert "尚无真实验证记录" in by_id["food.standard.configuration"].message
    assert "真实调用验证失败" in by_id["food.creative.configuration"].message


def test_live_evidence_overrides_stale_failed_generation_status():
    catalog = FoodCatalog(
        recipes={
            "standard": FoodRecipe(
                "standard",
                "标准粮",
                "",
                ExecutionProfile("ollama/local"),
                validation_status=FoodValidationStatus.FAILED,
            )
        }
    )
    evidence = [ModelEvidence("ollama/local", frozenset({"text"}), True, local=True)]

    suite = FoodValidationRunner().validate(catalog, evidence)
    standard = next(
        result for result in suite.results if result.check_id == "food.standard.configuration"
    )

    assert standard.status is CheckStatus.PASSED
