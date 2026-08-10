"""Provider-catalog projection used by first-run Setup model selection."""

from ai_runtime.providers.profiles import PROVIDER_CATALOG
from app.features.setup import StoredSetupModelOption

_APPROX_DOWNLOAD_MB = {
    "qwen2.5:0.5b": 398,
    "qwen3.5:0.8b": 1024,
    "gemma3:270m": 292,
}


class ProviderSetupCatalogAdapter:
    def list_setup_models(self) -> tuple[StoredSetupModelOption, ...]:
        return tuple(
            StoredSetupModelOption(
                model_id=item.model_id,
                label=f"{item.model_id}（推荐）" if item.recommended else item.model_id,
                approx_download_mb=_APPROX_DOWNLOAD_MB[item.model_id],
                recommended=item.recommended,
            )
            for item in PROVIDER_CATALOG.ollama_recommended_models
        )


__all__ = ("ProviderSetupCatalogAdapter",)
