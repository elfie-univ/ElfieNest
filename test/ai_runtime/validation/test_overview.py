from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.models import ExecutionProfile, FoodRecipe, FoodValidationStatus
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite
from ai_runtime.validation.overview import (
    RuntimeOverviewGenerator,
    RuntimeOverviewStore,
    build_overview,
    configured_provider_ids,
    render_provider_model_matrix,
)
from ai_runtime.validation.providers import DiscoveredModel


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
        ModelEvidence(
            "ollama/glm-5",
            frozenset({"text"}),
            True,
            display_name="GLM-5",
            latency_ms=600,
            local=True,
        ),
        ModelEvidence(
            "openai/provider-specific-id",
            frozenset({"text"}),
            True,
            display_name="GLM-5",
            latency_ms=900,
        ),
    ]
    catalog = FoodCatalog(
        recipes={
            "standard": FoodRecipe(
                "standard",
                "标准粮",
                "默认",
                ExecutionProfile("ollama/glm-5"),
                validation_status=FoodValidationStatus.PASSED,
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
    assert "✓ 600ms" in wide


def test_overview_store_keeps_current_and_history(tmp_path):
    store = RuntimeOverviewStore(tmp_path)
    first = store.save({"created_at": "first", "summary": {}})
    second = store.save({"created_at": "second", "summary": {}})

    assert first != second
    assert store.load_current()["created_at"] == "second"
    assert len(store.history()) == 2


def test_regenerate_removes_models_deleted_from_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig(config_home=str(tmp_path))
    evidence_store = ModelEvidenceStore(tmp_path / "evidence.yaml")
    evidence_store.merge(
        [
            ModelEvidence("ollama/deleted", frozenset({"text"}), False, local=True),
            ModelEvidence("cloud/keep", frozenset({"text"}), True),
        ]
    )
    monkeypatch.setattr(
        "ai_runtime.validation.overview.ProviderValidationRunner.verify_provider",
        lambda self, provider_id: CheckResult(
            f"provider.{provider_id}.health",
            CheckStatus.PASSED,
            "ok",
            provider=provider_id,
        ),
    )
    monkeypatch.setattr(
        "ai_runtime.validation.overview.discover_provider_models",
        lambda provider_id, config: [DiscoveredModel(provider_id, "current")],
    )
    monkeypatch.setattr(
        "ai_runtime.validation.overview.ProviderValidationRunner.verify_models",
        lambda self, provider_id, names: ValidationSuite(
            f"provider:{provider_id}",
            (
                CheckResult(
                    f"provider.{provider_id}.model.current",
                    CheckStatus.PASSED,
                    "ok",
                    provider=provider_id,
                    model="current",
                ),
            ),
        ),
    )

    report = RuntimeOverviewGenerator(
        config,
        evidence_store=evidence_store,
        food_store=FoodCatalogStore(tmp_path / "foods.yaml"),
    ).regenerate()

    assert set(evidence_store.load()) == {"ollama/current", "cloud/keep"}
    assert [row["model"] for row in report["models"]] == ["current"]


def test_regenerate_keeps_old_models_when_discovery_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig(config_home=str(tmp_path))
    evidence_store = ModelEvidenceStore(tmp_path / "evidence.yaml")
    evidence_store.merge(
        [ModelEvidence("ollama/keep", frozenset({"text"}), True, local=True)]
    )
    monkeypatch.setattr(
        "ai_runtime.validation.overview.ProviderValidationRunner.verify_provider",
        lambda self, provider_id: CheckResult(
            f"provider.{provider_id}.health",
            CheckStatus.PASSED,
            "ok",
            provider=provider_id,
        ),
    )

    def fail_discovery(provider_id, config):
        raise RuntimeError("offline")

    monkeypatch.setattr(
        "ai_runtime.validation.overview.discover_provider_models", fail_discovery
    )

    RuntimeOverviewGenerator(
        config,
        evidence_store=evidence_store,
        food_store=FoodCatalogStore(tmp_path / "foods.yaml"),
    ).regenerate()

    assert set(evidence_store.load()) == {"ollama/keep"}
