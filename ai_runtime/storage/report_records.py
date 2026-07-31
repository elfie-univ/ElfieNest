"""Typed report records and SQLite row decoders."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Optional


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
    details: Mapping[str, Any]


def run_from_row(row: sqlite3.Row) -> ReportRun:
    return ReportRun(
        run_id=str(row["run_id"]),
        scope=str(row["scope"]),
        trigger=str(row["trigger"]),
        started_at=str(row["started_at"]),
        finished_at=(
            str(row["finished_at"]) if row["finished_at"] is not None else None
        ),
        status=str(row["status"]),
    )


def observation_from_row(row: sqlite3.Row) -> ValidationObservation:
    raw_details = json.loads(str(row["details_json"]))
    details = raw_details if isinstance(raw_details, Mapping) else {}
    return ValidationObservation(
        observation_id=int(row["observation_id"]),
        run_id=str(row["run_id"]),
        subject_kind=str(row["subject_kind"]),
        subject_id=str(row["subject_id"]),
        observed_at=str(row["observed_at"]),
        status=str(row["status"]),
        latency_ms=(
            float(row["latency_ms"]) if row["latency_ms"] is not None else None
        ),
        time_to_first_token_ms=(
            float(row["time_to_first_token_ms"])
            if row["time_to_first_token_ms"] is not None
            else None
        ),
        error_category=(
            str(row["error_category"]) if row["error_category"] is not None else None
        ),
        error_message=(
            str(row["error_message"]) if row["error_message"] is not None else None
        ),
        details=dict(details),
    )
