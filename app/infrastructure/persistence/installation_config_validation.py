"""Validate configuration-bearing Setup milestones against the active data root."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ai_runtime.storage.config_store import read_yaml_mapping
from app.infrastructure.persistence.installation_storage_cutover import (
    InstallationCutoverError,
)


def validate_installation_milestone_config(
    config_path: Path,
    *,
    config_snapshot: Mapping[str, Any] | None,
    step: int,
    decision: str | None,
    ollama_endpoint: str | None,
    model_reference: str | None,
) -> None:
    config = (
        config_snapshot
        if config_snapshot is not None
        else read_yaml_mapping(config_path)
    )
    provider = _ollama_provider(config)
    if step == 2 and decision in {"bound_existing", "install_official"}:
        if not ollama_endpoint or provider.get("api_base") != ollama_endpoint:
            raise InstallationCutoverError(
                "当前配置未表达 Setup 的 Ollama endpoint"
            )
    if step == 4 and decision == "configured":
        if not model_reference or provider.get("selected_model") != model_reference:
            raise InstallationCutoverError(
                "当前配置未表达 Setup 的 configured model"
            )


def _ollama_provider(config: Mapping[str, Any]) -> Mapping[str, Any]:
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return {}
    provider = providers.get("ollama")
    return provider if isinstance(provider, dict) else {}
