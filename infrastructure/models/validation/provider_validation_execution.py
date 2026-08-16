"""Model-execution projection used by connection-level validation."""

from __future__ import annotations

from typing import Callable, Mapping

from pydantic import JsonValue

from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.provider_records import ProviderConnection
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.providers.profiles import get_product
from infrastructure.models.providers.request_profiles import default_request_profile_id

from .provider_validation_policy import (
    _credential_name,
    active_validation_models,
    connection_validation_fingerprint,
    representative_model_id,
)

SecretResolver = Callable[[str], str]


def model_execution_projection(
    connection: ProviderConnection,
    *,
    catalog: ProviderCatalog,
    system_defaults: Mapping[str, JsonValue],
    secret_resolver: SecretResolver = lambda _name: "",
) -> tuple[str, ModelExecutionConfig]:
    """Project one stable connection into the regular model adapter config."""
    profile = get_product(connection.catalog_id, catalog=catalog)
    if profile is None:
        raise ValueError("连接产品目录已经缺失")
    execution_id = connection.connection_id
    config = ModelExecutionConfig(
        provider_catalog=catalog,
        system_defaults=system_defaults,
    )
    active_models = active_validation_models(connection)
    config.providers[execution_id] = {
        "catalog_id": connection.catalog_id,
        "discovery_strategy": profile.discovery_strategy,
        "bundled_models": list(profile.bundled_models),
        "api_base": connection.api_base or profile.api_base,
        "api_mode": connection.api_mode or profile.api_mode,
        "request_profile_id": default_request_profile_id(
            connection.api_mode or profile.api_mode
        ),
        "request_profile_version": 1,
        "auth_type": connection.auth_type or profile.auth_type,
        "api_key": connection_api_key(connection, secret_resolver=secret_resolver),
        "config_fingerprint": connection_validation_fingerprint(
            connection,
            secret_resolver=secret_resolver,
        ),
        "models": [
            {"id": model.endpoint_model_id, "display_name": model.display_name}
            for model in active_models
        ],
        "model_profiles": {
            model.endpoint_model_id: {
                "request_profile_id": model.request_profile_id
                or default_request_profile_id(connection.api_mode or profile.api_mode),
                "request_profile_version": model.request_profile_version or 1,
            }
            for model in active_models
        },
        "test_model": representative_model_id(connection, catalog=catalog)
        or profile.test_model,
    }
    return execution_id, config


def connection_api_key(
    connection: ProviderConnection,
    *,
    secret_resolver: SecretResolver = lambda _name: "",
) -> str:
    """Resolve a connection secret without exposing it to API projections."""
    return secret_resolver(_credential_name(connection))
