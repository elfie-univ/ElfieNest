from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.store import FoodCatalog
from ai_runtime.validation.overview import build_overview


def test_overview_projects_food_health_without_generation_metadata():
    report = build_overview(LLMRuntimeConfig(), [], FoodCatalog())
    assert "food_generation_note" not in report
    assert report["summary"]["total_foods"] == 2
