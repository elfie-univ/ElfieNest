from runtime.food.models import ExecutionProfile, FoodRecipe
from runtime.food.store import FoodCatalog, FoodCatalogStore, fingerprint_source


def test_food_catalog_store_versions_and_detects_source_updates(tmp_path):
    path = tmp_path / "foods.yaml"
    history = tmp_path / "history"
    store = FoodCatalogStore(path, history)
    source = {"providers": {"ollama": ["local-model"]}}
    fingerprint = fingerprint_source(source)
    catalog = FoodCatalog(
        source_fingerprint=fingerprint,
        generation_sources=("model", "rules"),
        generation_note="模型建议与规则校验共同生成",
        recipes={
            "coarse": FoodRecipe(
                key="coarse",
                display_name="粗粮",
                description="本地",
                primary=ExecutionProfile(model="ollama/local-model"),
            )
        },
    )

    store.save(catalog)

    assert store.load().recipes["coarse"].primary.model == "ollama/local-model"
    assert store.load().generation_sources == ("model", "rules")
    assert store.has_update(fingerprint) is False
    assert store.has_update(fingerprint_source({"providers": {}})) is True

    store.save(catalog)
    assert len(list(history.glob("foods-*.yaml"))) == 1

    changed = FoodCatalog(
        version=2,
        source_fingerprint="changed",
        recipes=catalog.recipes,
    )
    store.save(changed)
    restored = store.rollback_latest()
    assert restored.source_fingerprint == fingerprint
