"""Provider-catalog projection used by first-run Setup model selection."""

from __future__ import annotations

from app.features.setup import StoredSetupModelOption
from infrastructure.models.providers.catalog import ProviderCatalog

_APPROX_DOWNLOAD_MB = {
    "qwen2.5:0.5b": 398,
    "qwen3.5:0.8b": 1024,
    "gemma3:270m": 292,
}


class ProviderSetupCatalogAdapter:
    def __init__(self, catalog: ProviderCatalog | None = None) -> None:
        if catalog is None:
            raise ValueError("ProviderSetupCatalogAdapter requires an injected catalog")
        self._catalog = catalog

    def list_setup_models(self) -> tuple[StoredSetupModelOption, ...]:
        return tuple(
            StoredSetupModelOption(
                model_id=item.model_id,
                label=f"{item.model_id}（推荐）" if item.recommended else item.model_id,
                approx_download_mb=_APPROX_DOWNLOAD_MB[item.model_id],
                recommended=item.recommended,
            )
            for item in self._catalog.ollama_recommended_models
        )


__all__ = ("ProviderSetupCatalogAdapter",)
