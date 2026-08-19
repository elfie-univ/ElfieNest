from __future__ import annotations

from app.features.configuration.providers import (
    StoredLocalModelCounts,
    StoredLocalProviderModelStatus,
    StoredLocalProviderStatus,
)
from infrastructure.persistence.ollama_status import SQLiteOllamaStatusCache
from infrastructure.persistence.reports.report_repository import ReportRepository


def test_ollama_status_cache_round_trips_through_runtime_observation(tmp_path) -> None:
    reports = ReportRepository(tmp_path / "reports.sqlite")
    cache = SQLiteOllamaStatusCache(reports)
    status = StoredLocalProviderStatus(
        state="healthy",
        endpoint="http://127.0.0.1:11434",
        version="0.1",
        memory_gb=8,
        recommended_model="recommended",
        installed_model_count=1,
        models=(
            StoredLocalProviderModelStatus(
                model_id="recommended",
                display_name="Recommended",
                installed=True,
                recommended=True,
                availability_status="available",
                available=True,
            ),
        ),
        model_counts=StoredLocalModelCounts(1, 1, 0, 0, 0),
        checked_at="2026-08-19T00:00:00+00:00",
    )

    cache.save(status)

    assert cache.load() == status
    observation = reports.latest("runtime", "ollama")
    assert observation is not None
    assert observation.status == "passed"
    assert observation.details["evidence_kind"] == "ollama_status"


def test_ollama_status_cache_shares_a_refresh_lease(tmp_path) -> None:
    cache = SQLiteOllamaStatusCache(ReportRepository(tmp_path / "reports.sqlite"))

    assert cache.try_acquire_refresh_lease("worker-a", lease_seconds=300) is True
    assert cache.try_acquire_refresh_lease("worker-b", lease_seconds=300) is False
    assert cache.release_refresh_lease("worker-a") is True
    assert cache.try_acquire_refresh_lease("worker-b", lease_seconds=300) is True
