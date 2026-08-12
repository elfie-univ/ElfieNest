"""Production Provider persistence adapter for Runtime Lab."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.models.providers.profiles import BUILTIN_PROFILES, get_product
from infrastructure.persistence.provider_connection_mutations import (
    delete_connection_with_secret,
    finalize_created_connection,
    replace_connection_with_secret,
)
from infrastructure.persistence.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
)


def save_provider_connection(
    provider_id: str,
    provider: Mapping[str, Any],
    pending_secret: Optional[str],
    *,
    store: Optional[ProviderConnectionStore] = None,
    secret_path: Optional[Path] = None,
) -> str:
    """Create or replace one v2 connection without persisting plaintext secrets."""
    connection_store = store or ProviderConnectionStore()
    existing = connection_store.load().connections.get(provider_id)
    catalog_id = _catalog_id(provider_id, provider, existing)
    profile = get_product(catalog_id)
    if profile is None:
        raise ValueError(f"未知 Provider 产品目录: {catalog_id}")

    models = _models(provider)
    alias = str(provider.get("display_name") or "").strip() or profile.name
    api_base = str(provider.get("api_base") or profile.api_base)
    api_mode = str(provider.get("api_mode") or profile.api_mode)
    auth_type = str(provider.get("auth_type") or profile.auth_type)

    if existing is None:
        connection = connection_store.create(
            catalog_id=catalog_id,
            alias=alias,
            api_base=api_base,
            api_mode=api_mode,
            auth_type=auth_type,
            models=models,
        )
        connection = finalize_created_connection(
            connection_store,
            connection,
            pending_secret,
            secret_path=secret_path,
        )
        return connection.connection_id

    connection = replace(
        existing,
        alias=alias,
        api_base=api_base,
        api_mode=api_mode,
        auth_type=auth_type,
        models=models,
    )
    connection = replace_connection_with_secret(
        connection_store,
        connection,
        pending_secret,
        secret_path=secret_path,
    )
    return connection.connection_id


def delete_provider_connection(
    connection_id: str,
    *,
    store: Optional[ProviderConnectionStore] = None,
    secret_path: Optional[Path] = None,
) -> bool:
    """Delete one configured connection and its connection-scoped secret."""
    connection_store = store or ProviderConnectionStore()
    return delete_connection_with_secret(
        connection_store,
        connection_id,
        secret_path=secret_path,
    )


def _catalog_id(
    provider_id: str,
    provider: Mapping[str, Any],
    existing: Optional[ProviderConnection],
) -> str:
    if existing is not None:
        return existing.catalog_id
    explicit = str(provider.get("catalog_id") or "").strip()
    if explicit:
        return explicit
    profile = BUILTIN_PROFILES.get(provider_id)
    if profile is not None:
        return profile.catalog_id
    return "custom_openai"


def _models(provider: Mapping[str, Any]) -> Tuple[ProviderModelRecord, ...]:
    raw_models = provider.get("models")
    if not isinstance(raw_models, list):
        return ()
    models = []
    for raw_model in raw_models:
        if not isinstance(raw_model, Mapping):
            continue
        model_id = str(raw_model.get("id") or "").strip()
        if not model_id:
            continue
        models.append(
            ProviderModelRecord(
                endpoint_model_id=model_id,
                display_name=str(raw_model.get("display_name") or model_id),
                source="manual",
            )
        )
    return tuple(models)


__all__ = ["delete_provider_connection", "save_provider_connection"]
