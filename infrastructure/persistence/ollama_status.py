"""SQLite-backed last-known Ollama service status."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.features.configuration.providers import (
    LocalProviderState,
    StoredLocalModelCounts,
    StoredLocalProviderModelStatus,
    StoredLocalProviderStatus,
)
from infrastructure.persistence.reports.report_repository import ReportRepository

_SUBJECT_KIND = "runtime"
_SUBJECT_ID = "ollama"
_EVIDENCE_KIND = "ollama_status"
_REFRESH_LEASE_KEY = "provider:ollama:status"
_STATES = frozenset(
    {
        "unknown",
        "absent",
        "healthy",
        "stopped",
        "deleted",
        "installing",
        "failed",
        "cancelled",
        "repair_required",
    }
)
_AVAILABILITY_STATES = frozenset({"available", "degraded", "unavailable", "unknown"})


class SQLiteOllamaStatusCache:
    """Persist status snapshots without the process-local task payload."""

    def __init__(self, reports: ReportRepository) -> None:
        self._reports = reports

    def load(self) -> StoredLocalProviderStatus | None:
        observation = self._reports.latest(_SUBJECT_KIND, _SUBJECT_ID)
        if (
            observation is None
            or observation.details.get("evidence_kind") != _EVIDENCE_KIND
        ):
            return None
        return _decode_status(observation.details, observation.observed_at)

    def save(self, status: StoredLocalProviderStatus) -> None:
        run_id = self._reports.start_run(
            scope="runtime:ollama",
            trigger="ollama_status",
            started_at=status.checked_at,
        )
        details = _encode_status(status)
        try:
            self._reports.append_observation(
                run_id=run_id,
                subject_kind=_SUBJECT_KIND,
                subject_id=_SUBJECT_ID,
                observed_at=status.checked_at,
                status=_observation_status(status.state),
                details=details,
            )
            self._reports.finish_run(
                run_id,
                status="complete",
                finished_at=status.checked_at,
            )
        except BaseException:
            try:
                self._reports.finish_run(
                    run_id,
                    status="failed",
                    finished_at=status.checked_at,
                )
            except Exception:
                pass
            raise

    def try_acquire_refresh_lease(
        self,
        owner_id: str,
        *,
        lease_seconds: int,
    ) -> bool:
        return self._reports.try_acquire_validation_lease(
            _REFRESH_LEASE_KEY,
            owner_id,
            lease_seconds=lease_seconds,
        )

    def release_refresh_lease(self, owner_id: str) -> bool:
        return self._reports.release_validation_lease(_REFRESH_LEASE_KEY, owner_id)


def _encode_status(status: StoredLocalProviderStatus) -> dict[str, Any]:
    # The task payload is deliberately not stored: it is process-local job
    # state. A later status scan replaces any task-derived state snapshot.
    return {
        "evidence_kind": _EVIDENCE_KIND,
        "state": status.state,
        "endpoint": status.endpoint,
        "version": status.version,
        "memory_gb": status.memory_gb,
        "recommended_model": status.recommended_model,
        "installed_model_count": status.installed_model_count,
        "model_counts": {
            "installed": status.model_counts.installed,
            "available": status.model_counts.available,
            "degraded": status.model_counts.degraded,
            "pending": status.model_counts.pending,
            "unavailable": status.model_counts.unavailable,
        },
        "models": [
            {
                "id": model.model_id,
                "display_name": model.display_name,
                "installed": model.installed,
                "recommended": model.recommended,
                "availability_status": model.availability_status,
                "available": model.available,
            }
            for model in status.models
        ],
    }


def _decode_status(
    details: Mapping[str, object],
    checked_at: str,
) -> StoredLocalProviderStatus | None:
    state = details.get("state")
    if not isinstance(state, str) or state not in _STATES:
        return None
    counts = _mapping(details.get("model_counts"))
    if counts is None:
        return None
    models_value = details.get("models")
    if not isinstance(models_value, list):
        return None
    models: list[StoredLocalProviderModelStatus] = []
    for value in models_value:
        model = _decode_model(value)
        if model is None:
            return None
        models.append(model)
    count_values = {
        key: _non_negative_int(counts.get(key))
        for key in ("installed", "available", "degraded", "pending", "unavailable")
    }
    if any(value is None for value in count_values.values()):
        return None
    memory_gb = _non_negative_int(details.get("memory_gb"))
    installed_model_count = _non_negative_int(details.get("installed_model_count"))
    if memory_gb is None or installed_model_count is None:
        return None
    return StoredLocalProviderStatus(
        state=state,  # type: ignore[arg-type]
        endpoint=_optional_text(details.get("endpoint")),
        version=_optional_text(details.get("version")),
        memory_gb=memory_gb,
        recommended_model=_optional_text(details.get("recommended_model")),
        installed_model_count=installed_model_count,
        models=tuple(models),
        model_counts=StoredLocalModelCounts(
            installed=count_values["installed"],  # type: ignore[arg-type]
            available=count_values["available"],  # type: ignore[arg-type]
            degraded=count_values["degraded"],  # type: ignore[arg-type]
            pending=count_values["pending"],  # type: ignore[arg-type]
            unavailable=count_values["unavailable"],  # type: ignore[arg-type]
        ),
        checked_at=checked_at,
    )


def _decode_model(value: object) -> StoredLocalProviderModelStatus | None:
    raw = _mapping(value)
    if raw is None:
        return None
    model_id = raw.get("id")
    display_name = raw.get("display_name")
    availability_status = raw.get("availability_status", "unknown")
    installed = raw.get("installed")
    recommended = raw.get("recommended")
    available = raw.get("available")
    if (
        not isinstance(model_id, str)
        or not isinstance(display_name, str)
        or not isinstance(availability_status, str)
        or availability_status not in _AVAILABILITY_STATES
        or not isinstance(installed, bool)
        or not isinstance(recommended, bool)
        or not isinstance(available, bool)
    ):
        return None
    return StoredLocalProviderModelStatus(
        model_id=model_id,
        display_name=display_name,
        installed=installed,
        recommended=recommended,
        availability_status=availability_status,  # type: ignore[arg-type]
        available=available,
    )


def _observation_status(state: LocalProviderState) -> str:
    if state == "healthy":
        return "passed"
    if state in {"unknown", "installing", "cancelled"}:
        return "warning"
    return "failed"


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _non_negative_int(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


__all__ = ("SQLiteOllamaStatusCache",)
