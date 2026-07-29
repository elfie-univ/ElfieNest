import pytest

from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore, fingerprint_source
from ai_runtime.models.model_reference import ModelReferenceError
from ai_runtime.storage.provider_connections import ProviderConnectionStore


def test_food_catalog_store_versions_and_detects_source_updates(tmp_path):
    path = tmp_path / "foods.yaml"
    history = tmp_path / "history"
    store = FoodCatalogStore(path, history)
    source = {"providers": {"ollama": ["local-model"]}}
    fingerprint = fingerprint_source(source)
    catalog = FoodCatalog(
        default_food="coarse",
        fallback_food="coarse",
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
    assert store.load().default_food == "coarse"
    assert store.load().fallback_food == "coarse"
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

    with pytest.raises(ModelReferenceError, match="connection_id/model_id"):
        store.save(catalog)


def test_food_store_migrates_legacy_provider_reference_to_connection(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    connection_store = ProviderConnectionStore()
    connection_store.create(
        catalog_id="openai_api",
        alias="OpenAI",
        legacy_provider_id="openai",
    )
    food_path = tmp_path / "configs" / "food-packages.yaml"
    food_path.parent.mkdir(parents=True, exist_ok=True)
    food_path.write_text(
        """
version: 1
default_food: standard
foods:
  standard:
    display_name: Standard
    description: Daily
    primary:
      model: openai/gpt-test
""".strip(),
        encoding="utf-8",
    )

    catalog = FoodCatalogStore(food_path, tmp_path / "history").load()

    assert catalog.version == 2
    assert catalog.recipes["standard"].primary.model == ("openai_api_0001/gpt-test")
    assert food_path.with_suffix(".yaml.v1.bak").exists()


def test_food_catalog_allows_stable_custom_package_ids_and_mutable_names(tmp_path):
    store = FoodCatalogStore(tmp_path / "foods.yaml", tmp_path / "history")
    food_id = "food_a1b2c3d4e5f6"
    catalog = FoodCatalog(
        default_food=food_id,
        recipes={
            food_id: FoodRecipe(
                key=food_id,
                display_name="原名称",
                description="",
                primary=ExecutionProfile(model="ollama/local"),
                local_only=True,
            )
        },
    )
    store.save(catalog)
    renamed = FoodRecipe(
        **{
            **store.load().recipes[food_id].__dict__,
            "display_name": "新名称",
        }
    )
    store.save(
        FoodCatalog(
            version=2,
            default_food=food_id,
            recipes={food_id: renamed},
        )
    )

    loaded = store.load()
    assert loaded.default_food == food_id
    assert list(loaded.recipes) == [food_id]
    assert loaded.recipes[food_id].display_name == "新名称"
