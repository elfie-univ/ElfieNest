from ai_runtime.food.models import FOOD_COMMON_ID
from ai_runtime.food.store import FoodCatalog
from app.features.configuration.food_access import visible_food_keys
from app.infrastructure.persistence.store import init_db


def test_common_is_globally_visible_and_emergency_not_selectable(tmp_path):
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    visible = visible_food_keys(db_path, 1, FoodCatalog())
    assert visible == (FOOD_COMMON_ID,)
