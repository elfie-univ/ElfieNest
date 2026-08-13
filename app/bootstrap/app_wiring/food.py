"""Production composition for the Food configuration boundary."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.features.configuration.food import FoodService
from infrastructure.models.food_technology import (
    FoodEvidencePort,
    ModelFoodTechnologyAdapter,
)
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import SQLiteFoodEvidenceAdapter
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_report_database_path,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.reports.report_repository import ReportRepository


def build_report_repository(db_path: str) -> ReportRepository:
    if db_path == ":memory:":
        path = (
            Path(tempfile.mkdtemp(prefix="elfienest-memory-reports-"))
            / "reports.sqlite"
        )
    else:
        path = get_report_database_path(data_home_from_db_path(db_path))
    return ReportRepository(path)


def build_food_service(
    db_path: str,
    *,
    evidence: FoodEvidencePort | None = None,
) -> FoodService:
    persistence = SQLiteFoodAdapter(db_path)
    evidence_port = evidence or build_food_evidence(db_path)
    return FoodService(
        catalog=persistence,
        technology=ModelFoodTechnologyAdapter(evidence_port),
        assignments=persistence,
    )


def build_food_evidence(
    db_path: str,
    *,
    report_repository: ReportRepository | None = None,
) -> SQLiteFoodEvidenceAdapter:
    provider_path = None
    if db_path != ":memory:":
        provider_path = final_root_layout(
            data_home_from_db_path(db_path)
        ).providers_config
    return SQLiteFoodEvidenceAdapter(
        ProviderConnectionStore(provider_path),
        report_repository or build_report_repository(db_path),
    )


__all__ = ("build_food_evidence", "build_food_service", "build_report_repository")
