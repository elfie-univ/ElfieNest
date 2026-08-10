from __future__ import annotations

from pathlib import Path

from app.orchestration.setup_installation import SetupOllamaBinding
from infrastructure.models import ProviderModelsAdapter
from infrastructure.models.setup_provider import SetupProviderAdapter


def test_setup_provider_round_trips_one_ollama_binding_and_model(
    tmp_path: Path,
) -> None:
    adapter = SetupProviderAdapter(
        ProviderModelsAdapter(tmp_path / "providers.yaml", tmp_path / "auth.env")
    )
    binding = SetupOllamaBinding(
        api_base="http://127.0.0.1:11434",
        platform="darwin",
        install_kind="official-script",
        launch_target="/Applications/Ollama.app",
        version="1.0",
    )

    adapter.save_ollama_binding(binding)
    reference = adapter.save_ollama_model("qwen2.5:0.5b")

    assert adapter.load_ollama_binding() == binding
    assert adapter.configured_model_reference("qwen2.5:0.5b") == reference
    assert adapter.configured_model_reference("missing") is None
