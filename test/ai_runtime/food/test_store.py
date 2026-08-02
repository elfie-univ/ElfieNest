import pytest

from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodPackage,
    ModelAssignment,
)
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.models.model_reference import ModelReferenceError
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)


def _setup_provider_connections():
    store = ProviderConnectionStore()
    store.replace(
        ProviderConnection(
            connection_id="ollama_0001",
            catalog_id="ollama",
            alias="Ollama",
            models=(ProviderModelRecord("local-model"),),
        )
    )
    store.replace(
        ProviderConnection(
            connection_id="cloud_0001",
            catalog_id="cloud",
            alias="Cloud",
            models=(ProviderModelRecord("main"),),
        )
    )


def test_food_catalog_store_saves_and_loads_packages(tmp_path, monkeypatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _setup_provider_connections()

    path = tmp_path / "foods.yaml"
    history = tmp_path / "history"
    store = FoodCatalogStore(path, history)

    catalog = FoodCatalog(
        packages={
            "coarse": FoodPackage(
                key="coarse",
                display_name="粗粮",
                primary=ModelAssignment(model="ollama_0001/local-model"),
            )
        }
    )

    store.save(catalog)

    loaded = store.load()
    assert loaded.packages["coarse"].primary.model == "ollama_0001/local-model"
    assert FOOD_EMERGENCY_ID in loaded.packages
    assert FOOD_COMMON_ID in loaded.packages


def test_food_catalog_store_keeps_version_history(tmp_path, monkeypatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _setup_provider_connections()

    path = tmp_path / "foods.yaml"
    history = tmp_path / "history"
    store = FoodCatalogStore(path, history)

    catalog = FoodCatalog(
        packages={
            "standard": FoodPackage(
                key="standard",
                display_name="标准粮",
                primary=ModelAssignment(model="cloud_0001/main"),
            )
        }
    )

    store.save(catalog)
    assert len(list(history.glob("foods-*.yaml"))) == 0

    catalog2 = FoodCatalog(
        packages={
            "standard": FoodPackage(
                key="standard",
                display_name="标准粮 Updated",
                primary=ModelAssignment(model="cloud_0001/main"),
            )
        }
    )
    store.save(catalog2)
    assert len(list(history.glob("foods-*.yaml"))) == 1

    restored = store.rollback_latest()
    assert restored.packages["standard"].display_name == "标准粮"


def test_food_catalog_store_rejects_invalid_model_reference(tmp_path, monkeypatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    store = FoodCatalogStore(tmp_path / "foods.yaml", tmp_path / "history")
    catalog = FoodCatalog(
        packages={
            "standard": FoodPackage(
                key="standard",
                display_name="标准粮",
                primary=ModelAssignment(model="qwen2.5:0.5b"),
            )
        }
    )

    with pytest.raises(ModelReferenceError, match="connection_id/model_id"):
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
