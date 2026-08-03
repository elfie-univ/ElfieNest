from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from ai_runtime.providers.catalog import load_provider_catalog
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from app.features.setup.ollama_owner import OllamaOwnerService
from app.infrastructure.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProbe,
)


def test_provider_catalog_exposes_the_three_ollama_recommendations() -> None:
    catalog = load_provider_catalog(Path("/definitely/missing/provider-catalog.yaml"))

    assert [(item.model_id, item.recommended) for item in catalog.ollama_recommended_models] == [
        ("qwen2.5:0.5b", True),
        ("qwen3.5:0.8b", False),
        ("gemma3:270m", False),
    ]


def test_owner_ollama_only_projects_recommended_models(tmp_path: Path) -> None:
    service = OllamaOwnerService(
        adapter=_HealthyOllamaAdapter(),
        provider_connection_store=ProviderConnectionStore(tmp_path / "providers.yaml"),
    )

    observation = service.inspect()

    assert [model.id for model in observation.models] == [
        "qwen2.5:0.5b",
        "qwen3.5:0.8b",
        "gemma3:270m",
    ]
    assert [model.recommended for model in observation.models] == [True, False, False]


def test_owner_ollama_rejects_legacy_model_for_download(tmp_path: Path) -> None:
    service = OllamaOwnerService(
        adapter=_HealthyOllamaAdapter(),
        provider_connection_store=ProviderConnectionStore(tmp_path / "providers.yaml"),
    )

    with pytest.raises(ValueError, match="候选清单"):
        service.pull_and_save(("legacy-local-model",))


class _HealthyOllamaAdapter(OllamaPlatformAdapter):
    platform: Literal["darwin"] = "darwin"

    def __init__(self) -> None:
        pass

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe("healthy", DEFAULT_OLLAMA_ENDPOINT, version="0.12.0")

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        return ("qwen2.5:0.5b", "legacy-local-model")
