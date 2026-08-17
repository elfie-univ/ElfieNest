"""Read-only persistence adapter for the Food model-health projection."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from app.features.configuration.food import (
    ModelHealthStatus,
    project_model_service_health,
)
from app.orchestration.lifecycle.runtime_snapshot import (
    ModelHealthProjection,
    ModelOverallState,
)
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import query_model_evidence
from infrastructure.persistence.layout.data_home import get_report_database_path
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_storage import ProviderStorageAdapter
from infrastructure.persistence.reports.report_repository import ReportRepository


class FoodModelHealthProjectionAdapter:
    """Project persisted Food evidence without probing or mutating providers."""

    def __init__(self, elfie_home: Path) -> None:
        self._layout = final_root_layout(elfie_home)
        self._provider_catalog = load_provider_catalog(
            self._layout.provider_catalog_config
        )

    def read(self) -> ModelHealthProjection:
        database = self._layout.nest_database
        if not database.is_file():
            return _unconfigured_projection()
        try:
            connection_store = ProviderConnectionStore(self._layout.providers_config)
            provider_storage = ProviderStorageAdapter(
                connection_store,
                secret_path=self._layout.auth_env,
            )
            report_database = get_report_database_path(self._layout.data_home)
            if report_database.is_file():
                evidence = query_model_evidence(
                    provider_catalog=self._provider_catalog,
                    repository=ReportRepository(report_database),
                    connection_store=connection_store,
                    secret_resolver=provider_storage.resolve_secret,
                )
            else:
                evidence = query_model_evidence(
                    provider_catalog=self._provider_catalog,
                    observations=(),
                    connection_store=connection_store,
                    secret_resolver=provider_storage.resolve_secret,
                )
            food = SQLiteFoodAdapter(database)
            packages = food.list_packages()
            assignments = food.list_assignments()
            evidence_items = tuple(evidence.values())
            health = project_model_service_health(
                packages,
                evidence_items,
                active_assignments=assignments,
            )
        except (OSError, RuntimeError, ValueError, sqlite3.Error):
            return _unconfigured_projection()
        return ModelHealthProjection(
            state=_state(health.status),
            common_state=_state(health.common_status),
            emergency_state=_state(health.emergency_status),
            revision=_projection_revision(packages, assignments, evidence_items),
        )


def _state(value: ModelHealthStatus) -> ModelOverallState:
    return {
        "healthy": ModelOverallState.READY,
        "degraded": ModelOverallState.DEGRADED,
        "unconfigured": ModelOverallState.UNCONFIGURED,
        "unavailable": ModelOverallState.UNAVAILABLE,
    }[value]


def _unconfigured_projection() -> ModelHealthProjection:
    return ModelHealthProjection(
        state=ModelOverallState.UNCONFIGURED,
        common_state=ModelOverallState.UNCONFIGURED,
        emergency_state=ModelOverallState.UNAVAILABLE,
    )


def _projection_revision(packages, assignments, evidence) -> int:
    """Derive a stable revision from persisted Food facts without writing state."""
    payload = {
        "packages": [
            {
                "food_id": item.food_id,
                "enabled": item.enabled,
                "archived": item.archived,
                "references": item.model_references,
            }
            for item in packages
        ],
        "assignments": [
            {
                "elfie_id": item.elfie_id,
                "food_id": item.main_food_id,
            }
            for item in assignments
        ],
        "evidence": [
            {
                "reference": item.reference,
                "status": item.status,
                "verified": item.verified,
                "fresh": item.fresh,
                "observed_at": item.observed_at,
            }
            for item in evidence
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return int(digest[:15], 16)


__all__ = ("FoodModelHealthProjectionAdapter",)
