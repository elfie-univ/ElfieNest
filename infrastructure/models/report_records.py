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


__all__ = ("ReportRun", "ValidationObservation")
