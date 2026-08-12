import os

from app.features.configuration.food import StoredModelEvidence
from elfie.brain.food_port import FoodAssignment, FoodCatalog, FoodPackage
from infrastructure.models.runtime_config import LLMRuntimeConfig
from infrastructure.models.runtime_overview import (
    build_overview,
    configured_provider_ids,
    render_provider_model_matrix,
)
from infrastructure.persistence.runtime_overview import RuntimeOverviewStore


def test_only_configured_providers_are_listed(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig(config_home=str(tmp_path))
    config.providers["openai"]["api_key"] = ""
    config.providers["openai"]["status"] = "inactive"
    config.providers["deepseek"]["api_key"] = "configured-locally"

    assert configured_provider_ids(config) == ["ollama", "deepseek"]


def test_overview_groups_same_model_across_providers_and_renders_responsively(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig(config_home=str(tmp_path))
    config.providers["openai"]["api_key"] = "configured-locally"
    evidence = [
        StoredModelEvidence(
            reference="ollama/glm-5",
            display_name="GLM-5",
            capabilities=frozenset({"text"}),
            verified=True,
            latency_ms=600,
            local=True,
        ),
        StoredModelEvidence(
            reference="openai/provider-specific-id",
            display_name="GLM-5",
            capabilities=frozenset({"text"}),
            verified=True,
            latency_ms=900,
        ),
    ]
    catalog = FoodCatalog(
        packages={
            "standard": FoodPackage(
                key="standard",
                display_name="标准粮",
                primary=FoodAssignment("ollama/glm-5"),
            )
        }
    )

    report = build_overview(config, evidence, catalog)
    narrow = "\n".join(render_provider_model_matrix(report, width=70))
    wide = "\n".join(render_provider_model_matrix(report, width=120))

    assert len(report["models"]) == 1
    assert len(report["models"][0]["endpoints"]) == 2
    assert "2/2" in narrow
    assert "ollama" in wide
    assert "openai" in wide
    assert "600ms" in wide


def test_overview_store_keeps_current_and_history(tmp_path):
    store = RuntimeOverviewStore(tmp_path)
    first = store.save({"created_at": "first", "summary": {}})
    second = store.save({"created_at": "second", "summary": {}})

    assert first != second
    assert store.load_current()["created_at"] == "second"
    assert len(store.history()) == 2


def test_overview_store_defaults_to_model_validation_directory(monkeypatch, tmp_path):
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    # When
    store = RuntimeOverviewStore()

    # Then
    assert store.directory == tmp_path / "reports" / "model-validations"
    path = store.save({"created_at": "manual", "summary": {}})
    if os.name != "nt":
        assert store.directory.stat().st_mode & 0o777 == 0o700
        assert path.stat().st_mode & 0o777 == 0o600
