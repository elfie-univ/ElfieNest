"""Model-discovery records and authoritative refresh merging."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Mapping

from infrastructure.models.provider_records import (
    ModelSource,
    ProviderModelRecord,
)
from infrastructure.models.providers.model_identity import (
    ModelIdentityCatalog,
    match_model_identity,
)
from infrastructure.models.providers.remote_catalog import fetch_remote_models

OBSOLETE_CLEANUP_AGE = timedelta(days=30)


def bundled_catalog_models(
    model_ids: Iterable[str],
    *,
    provider_id: str | None = None,
    identity_catalog: ModelIdentityCatalog | None = None,
) -> tuple[ProviderModelRecord, ...]:
    """Build records from the flattened bundled catalog model list."""
    return tuple(
        _catalog_model(
            model_id,
            source="bundled_catalog",
            provider_id=provider_id,
            identity_catalog=identity_catalog,
        )
        for model_id in dict.fromkeys(model_ids)
    )


def remote_catalog_models(
    catalog_id: str,
    *,
    fetcher: Callable[[str], tuple[str, ...]] = fetch_remote_models,
    provider_id: str | None = None,
    identity_catalog: ModelIdentityCatalog | None = None,
) -> tuple[ProviderModelRecord, ...]:
    """Build records from the configured remote catalog adapter."""
    return tuple(
        _catalog_model(
            model_id,
            source="remote_catalog",
            provider_id=provider_id or catalog_id,
            identity_catalog=identity_catalog,
        )
        for model_id in fetcher(catalog_id)
    )


def merge_refreshed_models(
    existing_models: tuple[ProviderModelRecord, ...],
    refreshed_models: tuple[ProviderModelRecord, ...],
    *,
    complete: bool = True,
    observed_at: str | None = None,
    authority_changed: bool = False,
    preserve_model_ids: Iterable[str] = (),
) -> tuple[ProviderModelRecord, ...]:
    """Merge one discovery result without deleting on a partial refresh.

    A complete authoritative refresh increments the missing counter for a
    discovered model that disappeared.  The first omission remains visible;
    the second marks it ``source_missing`` and makes it ineligible for normal
    validation.  Failed or incomplete refreshes preserve the prior inventory.
    """
    existing_by_id = {model.endpoint_model_id: model for model in existing_models}
    refreshed_by_id = {model.endpoint_model_id: model for model in refreshed_models}
    preserved_ids = set(preserve_model_ids)
    seen_at = observed_at or datetime.now(timezone.utc).isoformat()
    merged: list[ProviderModelRecord] = []
    for refreshed in refreshed_models:
        existing = existing_by_id.get(refreshed.endpoint_model_id)
        if existing is None:
            merged.append(
                replace(
                    refreshed,
                    available=True,
                    discovery_state="present",
                    consecutive_missing=0,
                    last_seen_at=seen_at,
                )
            )
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
                request_profile_id=(
                    existing.request_profile_id or refreshed.request_profile_id
                ),
                request_profile_version=(
                    existing.request_profile_version
                    or refreshed.request_profile_version
                ),
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
                supports_structured_output=(
                    existing.supports_structured_output
                    if existing.supports_structured_output is not None
                    else refreshed.supports_structured_output
                ),
                capability_evidence={
                    **refreshed.capability_evidence,
                    **existing.capability_evidence,
                },
                hidden=existing.hidden,
                retired=existing.retired,
                available=True,
                discovery_state="present",
                consecutive_missing=0,
                last_seen_at=seen_at,
            )
        )
    for existing in existing_models:
        if existing.endpoint_model_id in refreshed_by_id:
            continue
        if existing.endpoint_model_id in preserved_ids:
            # A currently serving Food may still depend on an endpoint that
            # disappeared from a product's curated catalog. Keep that exact
            # reference visible and protected; cleanup remains guarded by the
            # all-reference check instead of silently breaking production.
            merged.append(existing)
            continue
        if existing.source == "manual" or not complete:
            merged.append(existing)
            continue
        # A normal source needs two consecutive omissions.  An explicit
        # authority transition (for example the old broad Volcengine /models
        # inventory being replaced by the Coding Plan allowlist) is different:
        # those old IDs were never valid for the new product authority and are
        # hidden immediately while still retained for guarded cleanup/history.
        missing_count = existing.consecutive_missing + (
            2 if authority_changed and existing.consecutive_missing == 0 else 1
        )
        missing = missing_count >= 2
        merged.append(
            replace(
                existing,
                discovery_state="source_missing"
                if missing
                else existing.discovery_state,
                consecutive_missing=missing_count,
            )
        )
    return tuple(merged)


def cleanup_eligible_models(
    models: Iterable[ProviderModelRecord],
    *,
    referenced_model_ids: Iterable[str] = (),
    production_used_after: Mapping[str, str | None] | None = None,
    now: datetime | None = None,
    minimum_age: timedelta = OBSOLETE_CLEANUP_AGE,
) -> tuple[str, ...]:
    """Return source-managed obsolete IDs safe for explicit cleanup.

    The caller must repeat the all-reference check in its deletion transaction;
    this function only computes candidates and never mutates inventory.
    """
    current = _utc(now or datetime.now(timezone.utc))
    referenced = set(referenced_model_ids)
    used = production_used_after or {}
    eligible: list[str] = []
    for model in models:
        if (
            model.source == "manual"
            or model.discovery_state != "source_missing"
            or model.endpoint_model_id in referenced
        ):
            continue
        last_seen = _parse_timestamp(model.last_seen_at)
        if last_seen is None or current - last_seen < minimum_age:
            continue
        last_used = _parse_timestamp(used.get(model.endpoint_model_id))
        if last_used is not None and current - last_used < minimum_age:
            continue
        eligible.append(model.endpoint_model_id)
    return tuple(sorted(eligible))


def _catalog_model(
    model_id: str,
    *,
    source: ModelSource,
    provider_id: str | None = None,
    identity_catalog: ModelIdentityCatalog | None = None,
) -> ProviderModelRecord:
    identity = match_model_identity(model_id, model_id, catalog=identity_catalog)
    declaration = (
        None
        if provider_id is None or identity_catalog is None
        else identity_catalog.endpoint_declaration(provider_id, model_id)
    )
    return ProviderModelRecord(
        endpoint_model_id=model_id,
        display_name=model_id if declaration is None else declaration.display_name,
        # Canonical identity is display/grouping metadata only.  It must not
        # turn a generic model capability into an Endpoint capability.
        canonical_model_id=(identity.canonical_model_id if identity else None),
        source=source,
        context_window_tokens=(
            None if declaration is None else declaration.context_window_tokens
        ),
        max_output_tokens=(
            None if declaration is None else declaration.max_output_tokens
        ),
        supports_tools=(None if declaration is None else declaration.supports_tools),
        supports_vision=(None if declaration is None else declaration.supports_vision),
        supports_reasoning=(
            None if declaration is None else declaration.supports_reasoning
        ),
        supports_structured_output=(
            None if declaration is None else declaration.supports_structured_output
        ),
        capability_evidence=(
            {}
            if declaration is None
            else {
                name: "declared"
                for name, value in {
                    "tools": declaration.supports_tools,
                    "vision": declaration.supports_vision,
                    "reasoning": declaration.supports_reasoning,
                    "structured_output": declaration.supports_structured_output,
                }.items()
                if value is not None
            }
        ),
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
