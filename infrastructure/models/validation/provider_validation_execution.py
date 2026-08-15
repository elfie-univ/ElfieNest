"""Model-execution projection used by connection-level validation."""

from __future__ import annotations

from typing import Callable

from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.provider_records import ProviderConnection
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.providers.profiles import get_product

from .provider_validation_policy import (
    _credential_name,
    active_validation_models,
    representative_model_id,
)

SecretResolver = Callable[[str], str]


def model_execution_projection(
    connection: ProviderConnection,
    *,
    catalog: ProviderCatalog | None = None,
    secret_resolver: SecretResolver = lambda _name: "",
) -> tuple[str, ModelExecutionConfig]:
    """Project one stable connection into the regular model adapter config."""
    profile = get_product(connection.catalog_id, catalog=catalog)
    if profile is None:
        raise ValueError("连接产品目录已经缺失")
    execution_id = connection.connection_id
    config = ModelExecutionConfig(provider_catalog=catalog)
    active_models = active_validation_models(connection)
    config.providers[execution_id] = {
        "api_base": connection.api_base or profile.api_base,
        "api_mode": connection.api_mode or profile.api_mode,
        "auth_type": connection.auth_type or profile.auth_type,
        "api_key": connection_api_key(connection, secret_resolver=secret_resolver),
        "models": [
            {"id": model.endpoint_model_id, "display_name": model.display_name}
            for model in active_models
        ],
        "test_model": representative_model_id(connection) or profile.test_model,
    }
    return execution_id, config


def connection_api_key(
    connection: ProviderConnection,
    *,
    secret_resolver: SecretResolver = lambda _name: "",
) -> str:
    """Resolve a connection secret without exposing it to API projections."""
    return secret_resolver(_credential_name(connection))
