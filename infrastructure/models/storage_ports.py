"""Narrow technical Ports used to compose model capabilities.

These Ports intentionally expose semantic records only.  The model capability
must not know which YAML, secret or SQLite implementation supplies them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Optional, Protocol

from pydantic import JsonValue

from app.features.configuration.food import StoredModelEvidence

from .provider_records import ProviderConnection, ProviderModelRecord
from .report_records import ReportRun, ValidationObservation


class ProviderStorageError(RuntimeError):
    """Provider storage could not complete a requested operation."""


class ProviderStoragePort(Protocol):
    def load_connections(self) -> Mapping[str, ProviderConnection]: ...

    def create(
        self,
        *,
        catalog_id: str,
        alias: str,
        api_base: str = "",
        api_mode: str = "",
        auth_type: str = "",
        credential_ref: str = "",
        installation: Optional[Mapping[str, str]] = None,
        models: tuple[ProviderModelRecord, ...] = (),
    ) -> ProviderConnection: ...

    def replace(self, connection: ProviderConnection) -> None: ...

    def delete(self, connection_id: str) -> bool: ...

    def create_with_secret(
        self, connection: ProviderConnection, api_key: str | None
    ) -> ProviderConnection: ...

    def replace_with_secret(
        self,
        connection: ProviderConnection,
        api_key: str | None,
    ) -> ProviderConnection: ...

    def delete_with_secret(self, connection_id: str) -> bool: ...

    def has_secret(self, credential_ref: str) -> bool: ...

    def resolve_secret(self, credential_ref: str) -> str: ...


class ReportStoragePort(Protocol):
    def start_run(
        self,
        *,
        scope: str,
        trigger: str,
        started_at: str | None = None,
    ) -> str: ...

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: str | None = None,
    ) -> None: ...

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
    ) -> int: ...

    def current(
        self, *, subject_kind: str | None = None
    ) -> tuple[ValidationObservation, ...]: ...

    def as_of(
        self,
        timestamp: str,
        *,
        subject_kind: str | None = None,
    ) -> tuple[ValidationObservation, ...]: ...

    def latest(
        self,
        subject_kind: str,
        subject_id: str,
    ) -> ValidationObservation | None: ...

    def observations_for_run(
        self, run_id: str
    ) -> tuple[ValidationObservation, ...]: ...

    def observations_for_subject(
        self,
        subject_kind: str,
        subject_id: str,
    ) -> tuple[ValidationObservation, ...]: ...

    def get_run(self, run_id: str) -> ReportRun: ...

    def read_latest_model_validation(
        self,
        provider_id: str,
        model_id: str,
        *,
        validation_mode: Literal["any", "full"] = "any",
    ) -> Mapping[str, JsonValue]: ...

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
    ) -> int: ...

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
    ) -> int: ...

    def read_latest_provider_validation(
        self, provider_id: str
    ) -> Mapping[str, JsonValue]: ...


class ModelEvidencePort(Protocol):
    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]: ...

    def record_model_evidence(
        self,
        evidence: tuple[StoredModelEvidence, ...] | list[StoredModelEvidence],
        *,
        scope: str,
        trigger: str,
    ) -> str | None: ...


__all__ = (
    "ProviderStorageError",
    "ProviderStoragePort",
    "ReportStoragePort",
    "ModelEvidencePort",
)
