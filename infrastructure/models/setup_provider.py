"""Setup projection over the Providers-owned local connection Port."""

from __future__ import annotations

from typing import Optional, cast

from app.features.configuration import (
    ProviderLocalStatePort,
    ProviderPortError,
    StoredLocalProviderBinding,
)
from app.orchestration.setup_installation import (
    SetupInstallationPortError,
    SetupOllamaBinding,
)


class SetupProviderAdapter:
    def __init__(self, state: ProviderLocalStatePort) -> None:
        self._state = state

    def load_ollama_binding(self) -> SetupOllamaBinding | None:
        try:
            binding = self._state.load_local_binding()
        except ProviderPortError as error:
            raise SetupInstallationPortError("unable to read Ollama binding") from error
        if binding is None:
            return None
        return SetupOllamaBinding(
            api_base=binding.api_base,
            platform=binding.platform,
            install_kind=binding.install_kind,
            launch_target=binding.launch_target,
            version=binding.version,
            installer_source_url=binding.installer_source_url,
            installer_sha256=binding.installer_sha256,
        )

    def save_ollama_binding(self, binding: SetupOllamaBinding) -> None:
        try:
            self._state.save_local_binding(
                StoredLocalProviderBinding(
                    api_base=binding.api_base,
                    platform=binding.platform,
                    install_kind=binding.install_kind,
                    launch_target=binding.launch_target,
                    version=binding.version,
                    installer_source_url=binding.installer_source_url,
                    installer_sha256=binding.installer_sha256,
                )
            )
        except ProviderPortError as error:
            raise SetupInstallationPortError(
                "unable to persist Ollama binding"
            ) from error

    def save_ollama_model(self, model_id: str) -> str:
        try:
            return cast(str, self._state.save_local_model(model_id))
        except ProviderPortError as error:
            raise SetupInstallationPortError(
                "unable to persist Ollama model"
            ) from error

    def configured_model_reference(self, model_id: str) -> str | None:
        try:
            return cast(Optional[str], self._state.local_model_reference(model_id))
        except ProviderPortError as error:
            raise SetupInstallationPortError("unable to read Ollama model") from error


__all__ = ("SetupProviderAdapter",)
