import pytest

from ai_runtime.food.executor import NoAvailableFoodError
from ai_runtime.food.store import FoodCatalog
from ai_runtime.gateway.agent import RuntimeAgent


def test_runtime_never_selects_arbitrary_custom_food(monkeypatch):
    monkeypatch.setattr(
        RuntimeAgent, "_package_usable", staticmethod(lambda package: False)
    )
    with pytest.raises(NoAvailableFoodError) as error:
        RuntimeAgent._select_food_key(FoodCatalog(), "food_missing")
    assert error.value.code == "no_available_food"
