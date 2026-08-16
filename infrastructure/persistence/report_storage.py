"""Composition adapter for report queries used by model capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import JsonValue

from infrastructure.models.report_records import (
    ReportRun,
    ValidationObservation,
    ValidationRollup,
)
from infrastructure.persistence.reports.report_repository import ReportRepository
from infrastructure.persistence.reports.validation_reports import (
    read_latest_model_validation,
    read_latest_provider_validation,
    write_model_validation_report,
)


class ReportStorageAdapter:
    """Expose report persistence through the model-owned narrow Port."""

    def __init__(self, repository: ReportRepository) -> None:
        self._repository = repository

    def start_run(
        self,
        *,
        scope: str,
        trigger: str,
        started_at: str | None = None,
    ) -> str:
        return self._repository.start_run(
            scope=scope, trigger=trigger, started_at=started_at
        )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: str | None = None,
    ) -> None:
        self._repository.finish_run(run_id, status=status, finished_at=finished_at)

    def append_observation(
        self,
        *,
        run_id: str,
        subject_kind: str,
        subject_id: str,
        observed_at: str | None = None,
        status: str,
        latency_ms: float | None = None,
        time_to_first_token_ms: float | None = None,
        error_category: str | None = None,
        error_message: str | None = None,
        details: Mapping[str, JsonValue] | None = None,
    ) -> int:
        return self._repository.append_observation(
            run_id=run_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            observed_at=observed_at,
            status=status,
            latency_ms=latency_ms,
            time_to_first_token_ms=time_to_first_token_ms,
            error_category=error_category,
            error_message=error_message,
            details=details,
        )

    def current(
        self, *, subject_kind: str | None = None
    ) -> tuple[ValidationObservation, ...]:
        return self._repository.current(subject_kind=subject_kind)

    def as_of(
        self,
        timestamp: str,
        *,
        subject_kind: str | None = None,
    ) -> tuple[ValidationObservation, ...]:
        return self._repository.as_of(timestamp, subject_kind=subject_kind)

    def latest(
        self,
        subject_kind: str,
        subject_id: str,
    ) -> ValidationObservation | None:
        return self._repository.latest(subject_kind, subject_id)

    def observations_for_run(self, run_id: str) -> tuple[ValidationObservation, ...]:
        return self._repository.observations_for_run(run_id)

    def observations_for_subject(
        self,
        subject_kind: str,
        subject_id: str,
    ) -> tuple[ValidationObservation, ...]:
        return self._repository.observations_for_subject(subject_kind, subject_id)

    def compact_observations(self, before: str) -> int:
        return self._repository.compact_observations(before)

    def validation_rollups(
        self,
        *,
        subject_kind: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[ValidationRollup, ...]:
        return self._repository.validation_rollups(
            subject_kind=subject_kind,
            subject_id=subject_id,
        )

    def get_run(self, run_id: str) -> ReportRun:
        return self._repository.get_run(run_id)

    def read_latest_model_validation(
        self,
        provider_id: str,
        model_id: str,
        *,
        validation_mode: Literal["any", "full"] = "any",
    ) -> Mapping[str, JsonValue]:
        return read_latest_model_validation(
            provider_id,
            model_id,
            validation_mode=validation_mode,
            repository=self._repository,
        )

    def write_model_validation_report(
        self,
        provider_id: str,
        model_id: str,
        *,
        status: str,
        checked_at: str,
        latency_ms: float | None,
        latency_class: str | None,
        error: str | None,
        trigger: Literal["benchmark", "full"],
        run_id: str | None = None,
        details: Mapping[str, JsonValue] | None = None,
    ) -> int:
        return write_model_validation_report(
            provider_id,
            model_id,
            status=status,
            checked_at=checked_at,
            latency_ms=latency_ms,
            latency_class=latency_class,
            error=error,
            trigger=trigger,
            run_id=run_id,
            details=details,
            repository=self._repository,
        )

    def read_latest_provider_validation(
        self, provider_id: str
    ) -> Mapping[str, JsonValue]:
        return read_latest_provider_validation(provider_id, repository=self._repository)

    def write_provider_validation_report(
        self,
        provider_id: str,
        *,
        status: str,
        checked_at: str,
        latency_ms: float | None,
        error: str | None,
        trigger: Literal["batch", "single"],
        run_id: str | None = None,
        details: Mapping[str, JsonValue] | None = None,
    ) -> int:
        from infrastructure.persistence.reports.validation_reports import (
            write_provider_validation_report,
        )

        return write_provider_validation_report(
            provider_id,
            status=status,
            checked_at=checked_at,
            latency_ms=latency_ms,
            error=error,
            trigger=trigger,
            run_id=run_id,
            details=details,
            repository=self._repository,
        )


__all__ = ("ReportStorageAdapter",)
