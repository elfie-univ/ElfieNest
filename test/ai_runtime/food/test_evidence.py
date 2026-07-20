from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.planner import ModelEvidence


def test_model_evidence_store_merges_without_losing_previous_models(tmp_path):
    store = ModelEvidenceStore(tmp_path / "evidence.yaml")
    store.merge([ModelEvidence("ollama/local", frozenset({"text"}), True, local=True)])
    store.merge(
        [
            ModelEvidence(
                "cloud/vision", frozenset({"text", "vision"}), True, cost_grade=3
            )
        ]
    )

    loaded = store.load()
    assert set(loaded) == {"ollama/local", "cloud/vision"}
    assert loaded["cloud/vision"].capabilities == frozenset({"text", "vision"})


def test_model_evidence_store_preserves_display_name(tmp_path):
    store = ModelEvidenceStore(tmp_path / "evidence.yaml")
    store.merge(
        [
            ModelEvidence(
                "custom/odd-id",
                frozenset({"text"}),
                True,
                display_name="GLM-5",
            )
        ]
    )

    assert store.load()["custom/odd-id"].display_name == "GLM-5"


def test_store_enriches_old_evidence_from_known_model_catalog(tmp_path):
    store = ModelEvidenceStore(tmp_path / "evidence.yaml")
    store.merge(
        [
            ModelEvidence(
                "custom/xopkimik25",
                frozenset({"text"}),
                True,
                display_name="MiniMax-M2.5",
            )
        ]
    )

    loaded = store.load()["custom/xopkimik25"]
    assert loaded.display_name == "Kimi-K2.5"
    assert {"text", "reasoning", "vision"} <= loaded.capabilities


def test_replace_provider_removes_deleted_models_and_preserves_other_providers(
    tmp_path,
):
    store = ModelEvidenceStore(tmp_path / "evidence.yaml")
    store.merge(
        [
            ModelEvidence("ollama/deleted", frozenset({"text"}), False, local=True),
            ModelEvidence("ollama/current", frozenset({"text"}), True, local=True),
            ModelEvidence("cloud/vision", frozenset({"vision"}), True),
        ]
    )

    store.replace_provider(
        "ollama",
        [ModelEvidence("ollama/current", frozenset({"text"}), True, local=True)],
    )

    assert set(store.load()) == {"ollama/current", "cloud/vision"}
