import pytest

from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore, fingerprint_source
from ai_runtime.models.model_reference import ModelReferenceError


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


def test_food_catalog_store_rejects_a_bare_model_on_new_write(tmp_path):
    store = FoodCatalogStore(tmp_path / "foods.yaml", tmp_path / "history")
    catalog = FoodCatalog(
        recipes={
            "standard": FoodRecipe(
                key="standard",
                display_name="标准粮",
                description="",
                primary=ExecutionProfile(model="qwen2.5:0.5b"),
            )
        }
    )

    with pytest.raises(ModelReferenceError, match="provider_id/model_id"):
        store.save(catalog)

    assert not store.path.exists()


def test_food_catalog_store_defaults_to_final_config_paths(monkeypatch, tmp_path):
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    # When
    store = FoodCatalogStore()

    # Then
    assert store.path == tmp_path / "configs" / "food-packages.yaml"
    assert store.history_dir == tmp_path / "configs" / "food-packages-history"
