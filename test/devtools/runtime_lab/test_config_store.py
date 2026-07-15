import stat

import yaml

from devtools.elfie_lab.runtime_adapters import create_runtime
from devtools.runtime_lab import RuntimeLabConfigStore


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

    assert config.config_home == str(tmp_path / "development")
    assert config.providers["openai"]["api_key"] == ""
    assert store.root != production

    runtime = create_runtime("standard", str(store.root))
    assert runtime.inner.selected_model == "ollama/qwen3.5:0.8b"
    assert runtime.inner.runtime.food_catalog_store.path == store.root / "foods.yaml"


def test_provider_configuration_separates_secret_and_non_secret_data(tmp_path):
    store = RuntimeLabConfigStore(str(tmp_path / "runtime_lab"))

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
    assert runtime.inner.runtime.food_catalog_store.path == store.root / "foods.yaml"
