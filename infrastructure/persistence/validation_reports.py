"""Compatibility-shaped validation API backed by the report database."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional

from infrastructure.persistence.report_records import ValidationObservation
from infrastructure.persistence.report_repository import ReportRepository

REPORT_VERSION = 1
_PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REPORT_STATUS = frozenset({"failed", "passed"})
_PROVIDER_TRIGGER = frozenset({"batch", "single"})
_MODEL_TRIGGER = frozenset({"benchmark", "full"})


@dataclass(frozen=True)
class InvalidReportIdentityError(ValueError):
    identity: str

    def __str__(self) -> str:
        return f"验证报告标识不合法: {self.identity!r}"


def write_provider_validation_report(
    provider_id: str,
    *,
    status: str,
    checked_at: str,
    latency_ms: Optional[float],
    error: Optional[str],
    trigger: Literal["batch", "single"],
    run_id: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
) -> int:
    """Append one Provider observation and return its database identity."""
    _validate_provider_id(provider_id)
    _validate_status(status)
    if trigger not in _PROVIDER_TRIGGER:
        raise ValueError(f"不支持的 Provider 验证触发方式: {trigger}")
    repository = ReportRepository()
    owns_run = run_id is None
    if run_id is None:
        run_id = repository.start_run(
            scope=f"provider:{provider_id}",
            trigger=trigger,
            started_at=checked_at,
        )
    observation_id = repository.append_observation(
        run_id=run_id,
        subject_kind="provider",
        subject_id=provider_id,
        observed_at=checked_at,
        status=status,
        latency_ms=latency_ms,
        error_category=_error_category(error),
        error_message=error,
        details=details,
    )
    if owns_run:
        repository.finish_run(
            run_id,
            status="complete" if status == "passed" else "failed",
            finished_at=checked_at,
        )
    return observation_id


def read_latest_provider_validation(provider_id: str) -> dict[str, Any]:
    _validate_provider_id(provider_id)
    repository = ReportRepository()
    observation = repository.latest("provider", provider_id)
    if observation is None:
        return {}
    run = repository.get_run(observation.run_id)
    payload = {
        "version": REPORT_VERSION,
        "kind": "provider_validation",
        "provider_id": provider_id,
        "trigger": run.trigger,
        "checked_at": observation.observed_at,
        "status": observation.status,
        "latency_ms": observation.latency_ms,
        "error": observation.error_message,
    }
    if observation.details:
        payload["metadata"] = dict(observation.details)
    return payload


def write_model_validation_report(
    provider_id: str,
    model_id: str,
    *,
    status: str,
    checked_at: str,
    latency_ms: Optional[float],
    latency_class: Optional[str],
    error: Optional[str],
    trigger: Literal["benchmark", "full"],
    run_id: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
) -> int:
    """Append one endpoint-model observation without creating report files."""
    _validate_provider_id(provider_id)
    normalized_model_id = _validate_model_id(model_id)
    _validate_status(status)
    if trigger not in _MODEL_TRIGGER:
        raise ValueError(f"不支持的模型验证触发方式: {trigger}")
    repository = ReportRepository()
    owns_run = run_id is None
    if run_id is None:
        run_id = repository.start_run(
            scope=f"model:{provider_id}/{normalized_model_id}",
            trigger=trigger,
            started_at=checked_at,
        )
    metadata = {"latency_class": latency_class}
    metadata.update(details or {})
    observation_id = repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id=f"{provider_id}/{normalized_model_id}",
        observed_at=checked_at,
        status=status,
        latency_ms=latency_ms,
        error_category=_error_category(error),
        error_message=error,
        details=metadata,
    )
    if owns_run:
        repository.finish_run(
            run_id,
            status="complete" if status == "passed" else "failed",
            finished_at=checked_at,
        )
    return observation_id


def read_latest_model_validation(
    provider_id: str,
    model_id: str,
    *,
    validation_mode: Literal["any", "full"] = "any",
) -> dict[str, Any]:
    _validate_provider_id(provider_id)
    normalized_model_id = _validate_model_id(model_id)
    repository = ReportRepository()
    subject_id = f"{provider_id}/{normalized_model_id}"
    observation = (
        repository.latest("model", subject_id)
        if validation_mode == "any"
        else next(
            (
                item
                for item in repository.observations_for_subject("model", subject_id)
                if item.details.get("validation_mode") == "full"
                or repository.get_run(item.run_id).trigger == "full"
            ),
            None,
        )
    )
    if observation is None:
        return {}
    run = repository.get_run(observation.run_id)
    return _model_payload(
        provider_id,
        normalized_model_id,
        observation,
        run.trigger,
    )


def _model_payload(
    provider_id: str,
    model_id: str,
    observation: ValidationObservation,
    trigger: str,
) -> dict[str, Any]:
    payload = {
        "version": REPORT_VERSION,
        "kind": "model_validation",
        "provider_id": provider_id,
        "model_id": model_id,
        "trigger": trigger,
        "checked_at": observation.observed_at,
        "status": observation.status,
        "latency_ms": observation.latency_ms,
        "latency_class": observation.details.get("latency_class"),
        "error": observation.error_message,
    }
    if observation.details.get("validation_mode"):
        payload["validation_mode"] = observation.details["validation_mode"]
    if observation.details.get("full_run_id"):
        payload["full_run_id"] = observation.details["full_run_id"]
    return payload


def _validate_provider_id(provider_id: str) -> None:
    if _PROVIDER_ID_PATTERN.fullmatch(provider_id) is None:
        raise InvalidReportIdentityError(provider_id)


def _validate_model_id(model_id: str) -> str:
    normalized_model_id = model_id.strip()
    if not normalized_model_id or len(normalized_model_id) > 200:
        raise InvalidReportIdentityError(model_id)
    return normalized_model_id


def _validate_status(status: str) -> None:
    if status not in _REPORT_STATUS:
        raise ValueError(f"不支持的验证报告状态: {status}")


def _error_category(error: Optional[str]) -> Optional[str]:
    if not error:
        return None
    normalized = error.lower()
    if "auth" in normalized or "credential" in normalized or "401" in normalized:
        return "authentication"
    if "quota" in normalized or "billing" in normalized or "429" in normalized:
        return "quota"
    if "timeout" in normalized or "network" in normalized:
        return "network"
    return "unknown"
