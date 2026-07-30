from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID


def test_elfie_contract_has_one_primary_and_global_emergency():
    assert FOOD_COMMON_ID != FOOD_EMERGENCY_ID
