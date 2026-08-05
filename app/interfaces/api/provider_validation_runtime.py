"""Runtime projection used by connection-level model validation."""

from __future__ import annotations

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.providers.profiles import get_product
from ai_runtime.storage.provider_connections import ProviderConnection
from ai_runtime.storage.secrets import connection_secret_name, resolve_secret

from .provider_validation_policy import (
    active_validation_models,
    representative_model_id,
)


def runtime_projection(
    connection: ProviderConnection,
) -> tuple[str, LLMRuntimeConfig]:
    """Project one stable connection into the regular model adapter config."""
    profile = get_product(connection.catalog_id)
    if profile is None:
        raise ValueError("连接产品目录已经缺失")
    runtime_id = (
        connection.connection_id
        if connection.catalog_id == "custom_openai"
        else profile.legacy_provider_id
    )
    config = LLMRuntimeConfig()
    active_models = active_validation_models(connection)
    config.providers[runtime_id] = {
        "api_base": connection.api_base or profile.api_base,
        "api_mode": connection.api_mode or profile.api_mode,
        "auth_type": connection.auth_type or profile.auth_type,
        "api_key": connection_api_key(connection),
        "models": [
            {"id": model.endpoint_model_id, "display_name": model.display_name}
            for model in active_models
        ],
        "test_model": representative_model_id(connection) or profile.test_model,
    }
    return runtime_id, config


def connection_api_key(connection: ProviderConnection) -> str:
    """Resolve a connection secret without exposing it to API projections."""
    secret_name = connection.credential_ref or connection_secret_name(
        connection.connection_id
    )
    return resolve_secret(secret_name)
