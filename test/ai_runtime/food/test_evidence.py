from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)


def _configure_inventory() -> None:
    store = ProviderConnectionStore()
    store.replace(
        ProviderConnection(
            connection_id="ollama_0001",
            catalog_id="ollama",
            alias="Ollama",
            models=(
                ProviderModelRecord("local", supports_tools=True),
                ProviderModelRecord("current"),
                ProviderModelRecord("deleted"),
            ),
        )
    )
    store.replace(
        ProviderConnection(
            connection_id="custom_openai_0001",
            catalog_id="custom_openai",
            alias="Cloud",
            models=(
                ProviderModelRecord("vision", supports_vision=True),
                ProviderModelRecord("odd-id", display_name="GLM-5"),
                ProviderModelRecord("xopkimik25", display_name="MiniMax-M2.5"),
            ),
        )
    )


def test_model_evidence_store_merges_inventory_models(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _configure_inventory()
    store = ModelEvidenceStore(tmp_path / "reports.db")
    store.merge(
        [
            ModelEvidence(
                "ollama_0001/local",
                frozenset({"text"}),
                True,
                local=True,
            ),
            ModelEvidence(
                "custom_openai_0001/vision",
                frozenset({"text", "vision"}),
                True,
                cost_grade=3,
            ),
        ]
    )

    loaded = store.load()
    assert set(loaded) == {
        "ollama_0001/local",
        "custom_openai_0001/vision",
    }
    assert loaded["custom_openai_0001/vision"].capabilities == frozenset(
        {"text", "vision"}
    )


def test_model_evidence_store_preserves_inventory_display_name(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _configure_inventory()
    store = ModelEvidenceStore(tmp_path / "reports.db")
    store.merge(
        [
            ModelEvidence(
                "custom_openai_0001/odd-id",
                frozenset({"text"}),
                True,
                display_name="Ignored observation name",
            )
        ]
    )

    assert store.load()["custom_openai_0001/odd-id"].display_name == "GLM-5"


def test_store_enriches_evidence_from_known_model_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _configure_inventory()
    store = ModelEvidenceStore(tmp_path / "reports.db")
    store.merge(
        [
            ModelEvidence(
                "custom_openai_0001/xopkimik25",
                frozenset({"text"}),
                True,
            )
        ]
    )

    loaded = store.load()["custom_openai_0001/xopkimik25"]
    assert loaded.display_name == "Kimi-K2.5"
    assert {"text", "reasoning", "vision"} <= loaded.capabilities


def test_replace_provider_hides_removed_model_observation(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _configure_inventory()
    store = ModelEvidenceStore(tmp_path / "reports.db")
    store.merge(
        [
            ModelEvidence("ollama_0001/deleted", frozenset({"text"}), True),
            ModelEvidence("ollama_0001/current", frozenset({"text"}), True),
            ModelEvidence(
                "custom_openai_0001/vision",
                frozenset({"vision"}),
                True,
            ),
        ]
    )

    store.replace_provider(
        "ollama_0001",
        [
            ModelEvidence(
                "ollama_0001/current",
                frozenset({"text"}),
                True,
            )
        ],
    )

    assert set(store.load()) == {
        "ollama_0001/current",
        "custom_openai_0001/vision",
    }
