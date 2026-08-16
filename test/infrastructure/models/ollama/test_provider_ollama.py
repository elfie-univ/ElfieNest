from infrastructure.models.ollama.ollama_platform import OllamaBinding, OllamaProbe
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.persistence.provider_catalog import load_provider_catalog


class HealthyPlatform:
    platform = "linux"

    def probe(self, binding: OllamaBinding) -> OllamaProbe:
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        _ = binding
        return ("qwen2.5:0.5b",)


def test_provider_ollama_adapter_projects_the_authoritative_candidates() -> None:
    adapter = PublicOllamaProviderAdapter(
        platform=HealthyPlatform(), catalog=load_provider_catalog()
    )  # type: ignore[arg-type]
    binding = adapter.default_binding()

    assert binding.install_kind == "existing-public"
    probe = adapter.probe(binding)
    candidates = adapter.candidate_models()

    assert probe.state == "healthy"
    assert adapter.list_models(binding) == ("qwen2.5:0.5b",)
    assert [(item.model_id, item.recommended) for item in candidates] == [
        ("qwen2.5:0.5b", True),
        ("qwen3.5:0.8b", False),
        ("gemma3:270m", False),
    ]
