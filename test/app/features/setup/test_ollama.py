from __future__ import annotations

from pathlib import Path

import pytest

from app.features.setup.ollama import OllamaSetupService
from app.infrastructure.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaProbe,
)


def test_inspect_uses_the_fixed_local_endpoint_and_reports_installed_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup may inspect the documented local endpoint, but never scan arbitrary hosts."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    adapter = _InspectionAdapter()
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
    )

    observation = service.inspect()

    assert observation.probe.state == "healthy"
    assert observation.probe.endpoint == DEFAULT_OLLAMA_ENDPOINT
    assert observation.models == ("qwen2.5:3b",)
    assert [binding.api_base for binding in adapter.probed] == [DEFAULT_OLLAMA_ENDPOINT]


class _InspectionAdapter:
    platform = "linux"

    def __init__(self) -> None:
        self.probed: list[OllamaBinding] = []

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        self.probed.append(binding)
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        assert binding.api_base == DEFAULT_OLLAMA_ENDPOINT
        return ("qwen2.5:3b",)
