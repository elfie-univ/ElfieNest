"""Setup projection over the existing Provider connection fact source."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal, cast

from ai_runtime.storage.provider_connection_records import ProviderModelRecord
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderConnectionStoreError,
)
from app.orchestration.setup_installation import (
    SetupInstallationPortError,
    SetupOllamaBinding,
)


class SetupProviderAdapter:
    def __init__(self, connection_path: Path | None = None) -> None:
        self._store = ProviderConnectionStore(connection_path)

    def load_ollama_binding(self) -> SetupOllamaBinding | None:
        connection = self._ollama_connection()
        if connection is None or not connection.installation or not connection.api_base:
            return None
        raw = connection.installation
        try:
            platform = str(raw["platform"])
            if platform not in {"darwin", "linux", "win32"}:
                return None
            return SetupOllamaBinding(
                api_base=connection.api_base,
                platform=cast(Literal["darwin", "linux", "win32"], platform),
                install_kind=str(raw["install_kind"]),
                launch_target=str(raw["launch_target"]),
                version=str(raw.get("version", "")),
                installer_source_url=str(raw.get("installer_source_url", "")),
                installer_sha256=str(raw.get("installer_sha256", "")),
            )
        except KeyError:
            return None

    def save_ollama_binding(self, binding: SetupOllamaBinding) -> None:
        installation = {
            key: str(value)
            for key, value in asdict(binding).items()
            if value is not None
        }
        try:
            connection = self._ollama_connection()
            if connection is None:
                self._store.create(
                    catalog_id="ollama",
                    alias="Ollama",
                    api_base=binding.api_base,
                    api_mode="ollama",
                    auth_type="none",
                    installation=installation,
                )
                return
            self._store.replace(
                replace(
                    connection,
                    api_base=binding.api_base,
                    api_mode="ollama",
                    auth_type="none",
                    installation=installation,
                    enabled=True,
                    archived=False,
                )
            )
        except (OSError, ValueError, ProviderConnectionStoreError) as error:
            raise SetupInstallationPortError(
                "unable to persist Ollama binding"
            ) from error

    def save_ollama_model(self, model_id: str) -> str:
        try:
            connection = self._ollama_connection()
            if connection is None:
                raise SetupInstallationPortError("Ollama connection is missing")
            models = {item.endpoint_model_id: item for item in connection.models}
            models[model_id] = ProviderModelRecord(
                endpoint_model_id=model_id,
                display_name=model_id,
                source="official",
            )
            self._store.replace(replace(connection, models=tuple(models.values())))
            return f"{connection.connection_id}/{model_id}"
        except SetupInstallationPortError:
            raise
        except (OSError, ValueError, ProviderConnectionStoreError) as error:
            raise SetupInstallationPortError(
                "unable to persist Ollama model"
            ) from error

    def configured_model_reference(self, model_id: str) -> str | None:
        try:
            connection = self._ollama_connection()
        except (OSError, ValueError, ProviderConnectionStoreError) as error:
            raise SetupInstallationPortError("unable to read Ollama model") from error
        if connection is None or not any(
            item.endpoint_model_id == model_id for item in connection.models
        ):
            return None
        return f"{connection.connection_id}/{model_id}"

    def _ollama_connection(self) -> ProviderConnection | None:
        return next(
            (
                item
                for item in self._store.load().connections.values()
                if item.catalog_id == "ollama"
            ),
            None,
        )


__all__ = ("SetupProviderAdapter",)
