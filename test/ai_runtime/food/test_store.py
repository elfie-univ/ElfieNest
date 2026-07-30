from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from ai_runtime.food.store import FoodCatalogStore


def test_store_initializes_two_permanent_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    store = FoodCatalogStore(tmp_path / "food-packages.yaml", tmp_path / "history")
    catalog = store.load()
    assert list(catalog.packages) == [FOOD_EMERGENCY_ID, FOOD_COMMON_ID]
    text = store.path.read_text()
    assert "global_default_food_id: food_common" in text
    assert "global_emergency_food_id: food_emergency" in text
