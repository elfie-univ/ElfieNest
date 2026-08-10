import stat

import yaml

from ai_runtime.food.models import FoodPackage, ModelAssignment
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from infrastructure.persistence.store import init_db
from devtools.elfie_lab.runtime_adapters import (
    create_runtime,
    default_runtime_config_dir,
)
from devtools.runtime_lab import RuntimeLabConfigStore
from devtools.runtime_lab.config_store import PROVIDER_DEFAULTS


def _write_foods(root):
    root.mkdir(parents=True, exist_ok=True)
    init_db(str(root / "nest.db"))
    repository = SQLiteFoodPackageRepository(root / "nest.db")
    for package in (
            FoodPackage(
                key="standard",
                display_name="标准粮",
                primary=ModelAssignment("ollama/qwen3.5:0.8b"),
            ),
            FoodPackage(
                key="focus",
                display_name="清醒粮",
                primary=ModelAssignment("openai/example-model"),
            ),
    ):
        repository.create(package)


def test_development_runtime_config_does_not_read_production_config(
    tmp_path, monkeypatch
):
    production = tmp_path / "production"
    production.mkdir()
    (production / ".env").write_text(
        "OPENAI_API_KEY=production-only-secret\n", encoding="utf-8"
    )
    (production / "foods.yaml").write_text(
        "foods:\n  standard:\n    primary:\n      model: openai/production-only-model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ELFIE_HOME", str(production))
    monkeypatch.setenv("OPENAI_API_KEY", "process-only-secret")

    store = RuntimeLabConfigStore(str(tmp_path / "development"))
    config = store.load_runtime_config()
    _write_foods(store.root)

    assert config.config_home == str(tmp_path / "development")
    assert config.providers["openai"]["api_key"] == ""
    assert store.root != production

    runtime = create_runtime("standard", str(store.root))
    assert runtime.inner.selected_model == "ollama/qwen3.5:0.8b"
    assert runtime.inner.runtime.food_catalog_repository._db_path == str(store.root / "nest.db")


def test_elfie_lab_runtime_adapter_defaults_to_developer_root(tmp_path, monkeypatch):
    production_home = tmp_path / "production"
    developer_home = tmp_path / "developer"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(developer_home))

    config_dir = default_runtime_config_dir()

    assert config_dir == str(developer_home / "runtime_lab")
    assert config_dir != str(production_home)


def test_runtime_lab_defaults_use_the_catalog_test_model_for_vision(tmp_path):
    # Given: the Runtime Lab builds its isolated default document from the Provider catalog.
    store = RuntimeLabConfigStore(str(tmp_path / "runtime_lab"))

    # When: the document is materialized without any manual provider configuration.
    document = store.default_document()

    # Then: its vision slot keeps a current catalog model instead of the retired role map.
    assert document["multimodal_model"] == PROVIDER_DEFAULTS["ollama"]["test_model"]


def test_provider_configuration_separates_secret_and_non_secret_data(tmp_path):
    store = RuntimeLabConfigStore(str(tmp_path / "runtime_lab"))
    _write_foods(store.root)

    status = store.configure_provider(
        "openai",
        api_base="https://example.invalid/v1",
        api_mode="chat_completions",
        model="example-model",
        model_key="remote_deep",
        api_key="unit-test-secret",
    )

    document = yaml.safe_load(store.config_path.read_text(encoding="utf-8"))
    assert "unit-test-secret" not in store.config_path.read_text(encoding="utf-8")
    assert document["deep_provider"] == "openai"
    assert document["deep_model"] == "example-model"
    assert status["ready_for_attempt"] is True
    assert status["model_key"] == "remote_deep"
    assert store.env_path.read_text(encoding="utf-8").strip() == (
        "OPENAI_API_KEY=unit-test-secret"
    )
    assert stat.S_IMODE(store.env_path.stat().st_mode) == 0o600

    runtime = create_runtime("focus", str(store.root))
    assert runtime.inner.selected_provider == "openai"
    assert runtime.inner.selected_model == "openai/example-model"
    assert runtime.inner.runtime.food_catalog_repository._db_path == str(store.root / "nest.db")
