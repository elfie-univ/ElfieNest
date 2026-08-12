"""Test-only Bootstrap-equivalent Provider composition."""

from __future__ import annotations

import os
from pathlib import Path

from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.persistence.food_evidence import SQLiteFoodEvidenceAdapter
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
    evidence = SQLiteFoodEvidenceAdapter(
        store,
        report_repository,
    )
    return ProviderModelsAdapter(
        ProviderStorageAdapter(store, secret_path=secret_path),
        report_port,
        evidence,
    )


__all__ = ("provider_models_adapter",)
