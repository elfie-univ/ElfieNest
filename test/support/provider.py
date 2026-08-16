"""Test-only Bootstrap-equivalent Provider composition."""

from __future__ import annotations

import os
from pathlib import Path

from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.persistence.configuration.bundled_defaults import (
    load_system_defaults,
)
from infrastructure.persistence.food_evidence import SQLiteFoodEvidenceAdapter
from infrastructure.persistence.model_catalog import load_model_identities
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_storage import ProviderStorageAdapter
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.reports.report_repository import ReportRepository


def provider_models_adapter(
    provider_path: Path | None = None,
    secret_path: Path | None = None,
    *,
    reports=None,
) -> ProviderModelsAdapter:
    report_repository = (
        ReportRepository()
        if os.getenv("ELFIE_HOME")
        else ReportRepository(
            None if provider_path is None else provider_path.parent / "reports.sqlite"
        )
    )
    report_port = reports or ReportStorageAdapter(report_repository)
    store = ProviderConnectionStore(provider_path)
    provider_catalog = load_provider_catalog()
    provider_storage = ProviderStorageAdapter(store, secret_path=secret_path)
    evidence = SQLiteFoodEvidenceAdapter(
        store,
        report_repository,
        provider_catalog,
        secret_resolver=provider_storage.resolve_secret,
    )
    return ProviderModelsAdapter(
        provider_storage,
        report_port,
        evidence,
        catalog=provider_catalog,
        identity_catalog=load_model_identities(),
        system_defaults=load_system_defaults(),
    )


__all__ = ("provider_models_adapter",)
