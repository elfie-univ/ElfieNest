"""The intentionally small model catalog exposed by the first-run Setup flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ai_runtime.providers.profiles import PROVIDER_CATALOG


@dataclass(frozen=True)
class SetupModelOption:
    """One supported local model and the copy used by Setup to describe it."""

    model_id: str
    label: str
    approx_download_mb: int
    recommended: bool = False


_APPROX_DOWNLOAD_MB_BY_MODEL: Final[dict[str, int]] = {
    "qwen2.5:0.5b": 398,
    "qwen3.5:0.8b": 1024,
    "gemma3:270m": 292,
}


def _build_setup_model_catalog() -> tuple[SetupModelOption, ...]:
    return tuple(
        SetupModelOption(
            model_id=item.model_id,
            label=f"{item.model_id}（推荐）" if item.recommended else item.model_id,
            approx_download_mb=_APPROX_DOWNLOAD_MB_BY_MODEL[item.model_id],
            recommended=item.recommended,
        )
        for item in PROVIDER_CATALOG.ollama_recommended_models
    )


SETUP_MODEL_CATALOG: Final[tuple[SetupModelOption, ...]] = _build_setup_model_catalog()

_SETUP_MODELS_BY_ID: Final[dict[str, SetupModelOption]] = {
    option.model_id: option for option in SETUP_MODEL_CATALOG
}


def setup_model_options() -> tuple[SetupModelOption, ...]:
    """Return the fixed, ordered options without exposing mutable catalog state."""
    return SETUP_MODEL_CATALOG


def get_setup_model(model_id: str) -> SetupModelOption:
    """Resolve one bare model ID or reject arbitrary providers/models."""
    try:
        return _SETUP_MODELS_BY_ID[model_id]
    except KeyError as exc:
        raise ValueError("Setup 只支持固定的本地模型") from exc


def is_setup_model(model_id: str) -> bool:
    """Return whether a model ID is in the Setup allow-list."""
    return model_id in _SETUP_MODELS_BY_ID


__all__ = (
    "SETUP_MODEL_CATALOG",
    "SetupModelOption",
    "get_setup_model",
    "is_setup_model",
    "setup_model_options",
)
