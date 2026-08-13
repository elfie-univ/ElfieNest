"""Persistence-backed source for the model Runtime configuration projection."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, cast

from pydantic import JsonValue

from infrastructure.models.providers.profiles import get_product
from infrastructure.models.runtime_config import LLMRuntimeConfig
from infrastructure.persistence.configuration.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
)
from infrastructure.persistence.configuration.oauth_credentials import (
    OAuthCredentialAdapter,
    OAuthCredentialStore,
)
from infrastructure.persistence.configuration.runtime_settings import (
    read_runtime_settings,
)
from infrastructure.persistence.configuration.secrets import (
    connection_secret_name,
    provider_secret_name,
    read_secrets,
    resolve_secret,
)
from infrastructure.persistence.layout.data_home import (
    get_env_path,
    get_provider_config_path,
)
from infrastructure.persistence.provider_connections import ProviderConnectionStore


class LocalRuntimeConfigSource:
    """Bind the Runtime model to the current local data-root facts."""

    def __init__(self, oauth_credentials: OAuthCredentialAdapter | None = None) -> None:
        self.oauth_credentials = oauth_credentials or OAuthCredentialAdapter()

    def load_env(self, config_home: Optional[Path]) -> Mapping[str, str]:
        return cast(
            Mapping[str, str],
            read_secrets(config_home / ".env" if config_home else get_env_path()),
        )

    def load_settings(self, config_home: Optional[Path]) -> Mapping[str, JsonValue]:
        try:
            if config_home is None:
                return cast(Mapping[str, JsonValue], read_runtime_settings())
            path = config_home / "config.yaml"
            return read_yaml_mapping(path) if path.exists() else {}
        except ConfigStoreError:
            return {}

    def load_connections(self) -> Mapping[str, Mapping[str, JsonValue]]:
        path = get_provider_config_path()
        if not path.exists():
            return {}
        document = ProviderConnectionStore(path).load()
        providers: dict[str, Mapping[str, JsonValue]] = {}
        for connection_id, connection in document.connections.items():
            if not connection.enabled or connection.archived:
                continue
            profile = get_product(connection.catalog_id)
            if profile is None:
                continue
            secret_name = connection.credential_ref or connection_secret_name(
                connection_id
            )
            oauth = (
                self.oauth_credentials.load(secret_name)
                if secret_name.startswith("oauth.")
                else None
            )
            providers[connection_id] = {
                "catalog_id": connection.catalog_id,
                "display_name": connection.alias,
                "api_base": connection.api_base or profile.api_base,
                "api_mode": connection.api_mode or profile.api_mode,
                "auth_type": connection.auth_type or profile.auth_type,
                "api_key_env": secret_name,
                "api_key": oauth.access_token if oauth is not None else resolve_secret(secret_name),
                "credential_ref": secret_name,
                "account_id": oauth.account_id if oauth is not None else None,
                "models": [
                    {
                        "id": model.endpoint_model_id,
                        "display_name": model.display_name,
                    }
                    for model in connection.models
                    if not model.hidden and not model.retired and model.available
                ],
            }
        return providers

    def resolve_secret(self, name: str, config_home: Optional[Path]) -> str:
        if config_home is not None:
            secrets = cast(Mapping[str, str], read_secrets(config_home / ".env"))
            return secrets.get(name, "")
        return resolve_secret(name)

    def provider_secret_name(self, provider_id: str) -> str:
        return provider_secret_name(provider_id)


def load_runtime_config(config_home: str | None = None) -> LLMRuntimeConfig:
    oauth_credentials = OAuthCredentialAdapter(
        None
        if config_home is None
        else OAuthCredentialStore(Path(config_home) / "credentials" / "oauth")
    )
    return LLMRuntimeConfig(
        config_home=config_home,
        source=LocalRuntimeConfigSource(oauth_credentials),
        oauth_credentials=oauth_credentials,
    )


__all__ = ("LocalRuntimeConfigSource", "load_runtime_config")
