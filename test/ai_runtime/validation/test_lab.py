from ai_runtime.food.store import FoodCatalogStore


def test_runtime_lab_store_uses_contract_catalog(tmp_path):
    catalog = FoodCatalogStore(tmp_path / "foods.yaml", tmp_path / "history").load()
    assert [item.system_role for item in catalog.ordered_packages()] == [
        "emergency",
        "common",
    ]
