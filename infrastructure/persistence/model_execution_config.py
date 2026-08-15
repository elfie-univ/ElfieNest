"""Persistence-backed source for model-execution configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, cast

from pydantic import JsonValue

from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.providers.request_profiles import default_request_profile_id
from infrastructure.models.validation.provider_validation_policy import (
    connection_validation_fingerprint,
)
from infrastructure.persistence.configuration.config_store import ConfigStoreError
from infrastructure.persistence.configuration.documents import (
    ConfigDocumentError,
    ConfigDocumentId,
    RuntimeConfigSource,
)
from infrastructure.persistence.configuration.oauth_credentials import (
    OAuthCredentialAdapter,
    OAuthCredentialStore,
)
from infrastructure.persistence.configuration.runtime_settings import (
    read_runtime_settings,
    read_tool_settings,
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
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import ProviderConnectionStore


class LocalModelExecutionConfigSource:
    """Bind model execution to the current local data-root facts."""

    def __init__(
        self,
        oauth_credentials: OAuthCredentialAdapter | None = None,
        *,
        provider_catalog: ProviderCatalog | None = None,
    ) -> None:
        self.oauth_credentials = oauth_credentials or OAuthCredentialAdapter()
        self.provider_catalog = provider_catalog or load_provider_catalog()

    def load_env(self, config_home: Optional[Path]) -> Mapping[str, str]:
        path = (
            final_root_layout(config_home).auth_env
            if config_home is not None
            else get_env_path()
        )
        return cast(
            Mapping[str, str],
            read_secrets(path),
        )

    def load_settings(self, config_home: Optional[Path]) -> Mapping[str, JsonValue]:
        try:
            if config_home is None:
                runtime = read_runtime_settings()
                tools = read_tool_settings().get("tools", {})
            else:
                source = RuntimeConfigSource(
                    final_root_layout(config_home).data_home / "configs"
                )
                runtime_document = source.load(ConfigDocumentId.RUNTIME_SETTINGS)
                runtime = (
                    {} if runtime_document is None else dict(runtime_document.document)
                )
                runtime.pop("version", None)
                tool_document = source.load(ConfigDocumentId.TOOL_SETTINGS)
                tools = (
                    {}
                    if tool_document is None
                    else dict(tool_document.document).get("tools", {})
                )
            if tools:
                runtime_policy = runtime.get("runtime_policy")
                if not isinstance(runtime_policy, dict):
                    runtime_policy = {}
                    runtime["runtime_policy"] = runtime_policy
                runtime_policy["tools"] = tools
            return runtime
        except (ConfigDocumentError, ConfigStoreError):
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
            profile = self.provider_catalog.products.get(connection.catalog_id)
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
                "api_key": oauth.access_token
                if oauth is not None
                else resolve_secret(secret_name),
                "credential_ref": secret_name,
                "request_profile_id": default_request_profile_id(
                    connection.api_mode or profile.api_mode
                ),
                "request_profile_version": 1,
                "account_id": oauth.account_id if oauth is not None else None,
                "config_fingerprint": connection_validation_fingerprint(
                    connection,
                    secret_resolver=(
                        (
                            lambda _name, token=oauth: ""
                            if token is None
                            else token.access_token
                        )
                        if secret_name.startswith("oauth.")
                        else resolve_secret
                    ),
                ),
                "models": [
                    {
                        "id": model.endpoint_model_id,
                        "display_name": model.display_name,
                    }
                    for model in connection.models
                    if (
                        not model.hidden
                        and not model.retired
                        and model.discovery_state == "present"
                    )
                ],
                "model_profiles": {
                    model.endpoint_model_id: {
                        "request_profile_id": model.request_profile_id
                        or default_request_profile_id(
                            connection.api_mode or profile.api_mode
                        ),
                        "request_profile_version": model.request_profile_version or 1,
                    }
                    for model in connection.models
                    if (
                        not model.hidden
                        and not model.retired
                        and model.discovery_state == "present"
                    )
                },
            }
        return providers

    def resolve_secret(self, name: str, config_home: Optional[Path]) -> str:
        if config_home is not None:
            secrets = cast(
                Mapping[str, str],
                read_secrets(final_root_layout(config_home).auth_env),
            )
            return secrets.get(name, "")
        return resolve_secret(name)

    def provider_secret_name(self, provider_id: str) -> str:
        return provider_secret_name(provider_id)


def load_model_execution_config(config_home: str | None = None) -> ModelExecutionConfig:
    provider_catalog = load_provider_catalog()
    oauth_credentials = OAuthCredentialAdapter(
        None
        if config_home is None
        else OAuthCredentialStore(
            final_root_layout(Path(config_home)).oauth_credentials
        )
    )
    return ModelExecutionConfig(
        config_home=config_home,
        provider_catalog=provider_catalog,
        source=LocalModelExecutionConfigSource(
            oauth_credentials,
            provider_catalog=provider_catalog,
        ),
        oauth_credentials=oauth_credentials,
    )


__all__ = ("LocalModelExecutionConfigSource", "load_model_execution_config")
