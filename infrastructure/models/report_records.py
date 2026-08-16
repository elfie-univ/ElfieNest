"""Typed report records shared by model projections and persistence adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from pydantic import JsonValue


@dataclass(frozen=True)
class ReportRun:
    run_id: str
    scope: str
    trigger: str
    started_at: str
    finished_at: Optional[str]
    status: str


@dataclass(frozen=True)
class ValidationObservation:
    observation_id: int
    run_id: str
    subject_kind: str
    subject_id: str
    observed_at: str
    status: str
    latency_ms: Optional[float]
    time_to_first_token_ms: Optional[float]
    error_category: Optional[str]
    error_message: Optional[str]
    details: Mapping[str, JsonValue]


@dataclass(frozen=True)
class ValidationRollup:
    """Content-free aggregate retained after raw observations expire."""

    subject_kind: str
    subject_id: str
    bucket_start: str
    observation_count: int
    passed_count: int
    failed_count: int
    warning_count: int
    skipped_count: int
    average_latency_ms: Optional[float]
    min_latency_ms: Optional[float]
    max_latency_ms: Optional[float]
    first_observed_at: str
    last_observed_at: str


__all__ = ("ReportRun", "ValidationObservation", "ValidationRollup")
