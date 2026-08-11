"""Model-discovery records and non-destructive refresh merging."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Iterable

from ai_runtime.providers.model_identity import match_model_identity
from ai_runtime.providers.remote_catalog import fetch_remote_models
from infrastructure.persistence.provider_connections import (
    ModelSource,
    ProviderModelRecord,
)


def bundled_catalog_models(model_ids: Iterable[str]) -> tuple[ProviderModelRecord, ...]:
    """Build records from the flattened bundled catalog model list."""
    return tuple(
        _catalog_model(model_id, source="bundled_catalog")
        for model_id in dict.fromkeys(model_ids)
    )


def remote_catalog_models(
    catalog_id: str,
    *,
    fetcher: Callable[[str], tuple[str, ...]] = fetch_remote_models,
) -> tuple[ProviderModelRecord, ...]:
    """Build records from the configured remote catalog adapter."""
    return tuple(
        _catalog_model(model_id, source="remote_catalog")
        for model_id in fetcher(catalog_id)
    )


def merge_refreshed_models(
    existing_models: tuple[ProviderModelRecord, ...],
    refreshed_models: tuple[ProviderModelRecord, ...],
) -> tuple[ProviderModelRecord, ...]:
    """Keep manual overrides while replacing discovered catalog availability."""
    existing_by_id = {model.endpoint_model_id: model for model in existing_models}
    refreshed_by_id = {model.endpoint_model_id: model for model in refreshed_models}
    merged: list[ProviderModelRecord] = []
    for refreshed in refreshed_models:
        existing = existing_by_id.get(refreshed.endpoint_model_id)
        if existing is None:
            merged.append(refreshed)
            continue
        merged.append(
            replace(
                refreshed,
                display_name=(
                    existing.display_name
                    if existing.source == "manual"
                    else refreshed.display_name
                ),
                canonical_model_id=(
                    existing.canonical_model_id or refreshed.canonical_model_id
                ),
                source=("manual" if existing.source == "manual" else refreshed.source),
                context_window_tokens=(
                    existing.context_window_tokens or refreshed.context_window_tokens
                ),
                max_output_tokens=(
                    existing.max_output_tokens or refreshed.max_output_tokens
                ),
                supports_tools=(
                    existing.supports_tools
                    if existing.supports_tools is not None
                    else refreshed.supports_tools
                ),
                supports_vision=(
                    existing.supports_vision
                    if existing.supports_vision is not None
                    else refreshed.supports_vision
                ),
                supports_reasoning=(
                    existing.supports_reasoning
                    if existing.supports_reasoning is not None
                    else refreshed.supports_reasoning
                ),
                hidden=existing.hidden,
                retired=existing.retired,
                available=True,
            )
        )
    for existing in existing_models:
        if existing.endpoint_model_id not in refreshed_by_id:
            merged.append(
                existing
                if existing.source == "manual"
                else replace(existing, available=False)
            )
    return tuple(merged)


def _catalog_model(model_id: str, *, source: ModelSource) -> ProviderModelRecord:
    identity = match_model_identity(model_id, model_id)
    return ProviderModelRecord(
        endpoint_model_id=model_id,
        display_name=model_id,
        canonical_model_id=(identity.canonical_model_id if identity else None),
        context_window_tokens=(identity.context_window_tokens if identity else None),
        max_output_tokens=(identity.max_output_tokens if identity else None),
        supports_tools=(identity.supports_tools if identity else None),
        supports_vision=(identity.supports_vision if identity else None),
        supports_reasoning=(identity.supports_reasoning if identity else None),
        source=source,
    )
