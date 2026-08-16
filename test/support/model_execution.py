"""Explicit bundled dependencies for isolated model-execution tests."""

from __future__ import annotations

from typing import Any

from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.persistence.configuration.bundled_defaults import (
    load_system_defaults,
)
from infrastructure.persistence.provider_catalog import load_provider_catalog


def model_execution_config(**kwargs: Any) -> ModelExecutionConfig:
    """Build the same injected projection used by the production composition root."""
    kwargs.setdefault("provider_catalog", load_provider_catalog())
    kwargs.setdefault("system_defaults", load_system_defaults())
    return ModelExecutionConfig(**kwargs)


__all__ = ("model_execution_config",)
