"""Append-oriented SQLite repository for AI Runtime reports."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from infrastructure.persistence.layout.data_home import get_report_database_path
from infrastructure.persistence.reports.report_queries import (
    latest_observations,
    observations_for_run,
    observations_for_subject,
)
from infrastructure.persistence.reports.report_records import (
    ReportRun,
    ValidationObservation,
    run_from_row,
)
from infrastructure.persistence.reports.report_schema import (
    connect_report_database,
    initialize_report_database,
)

_RUN_STATUSES = frozenset({"running", "complete", "partial", "failed"})
_SUBJECT_KINDS = frozenset({"provider", "model", "food", "fallback", "tool", "runtime"})
_OBSERVATION_STATUSES = frozenset({"passed", "failed", "warning", "skipped"})


class ReportRepository:
    """The sole writer and query boundary for Runtime validation evidence."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or get_report_database_path()
        initialize_report_database(self.path)

    def start_run(
        self,
        *,
        scope: str,
        trigger: str,
        started_at: Optional[str] = None,
    ) -> str:
        run_id = f"run_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO report_runs (
                    run_id, scope, trigger, started_at, status
                ) VALUES (?, ?, ?, ?, 'running')
                """,
                (
                    run_id,
                    _required_text(scope, "scope"),
                    _required_text(trigger, "trigger"),
                    _timestamp(started_at),
                ),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: Optional[str] = None,
    ) -> None:
        if status not in _RUN_STATUSES - {"running"}:
            raise ValueError(f"不支持的报告运行状态: {status}")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE report_runs
                SET status = ?, finished_at = ?
                WHERE run_id = ? AND status = 'running'
                """,
                (status, _timestamp(finished_at), run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"报告运行不存在或已经结束: {run_id}")

    def append_observation(
        self,
        *,
        run_id: str,
        subject_kind: str,
        subject_id: str,
        observed_at: Optional[str] = None,
        status: str,
        latency_ms: Optional[float] = None,
        time_to_first_token_ms: Optional[float] = None,
        error_category: Optional[str] = None,
        error_message: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> int:
        _validate_observation(subject_kind, status)
        _validate_latency(latency_ms, "latency_ms")
        _validate_latency(time_to_first_token_ms, "time_to_first_token_ms")
        detail_json = json.dumps(
            dict(details or {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            run = connection.execute(
                "SELECT status FROM report_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ValueError(f"报告运行不存在: {run_id}")
            if run["status"] != "running":
                raise ValueError(f"报告运行已经结束: {run_id}")
            cursor = connection.execute(
                """
                INSERT INTO validation_observations (
                    run_id, subject_kind, subject_id, observed_at, status,
                    latency_ms, time_to_first_token_ms, error_category,
                    error_message, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    subject_kind,
                    _required_text(subject_id, "subject_id"),
                    _timestamp(observed_at),
                    status,
                    latency_ms,
                    time_to_first_token_ms,
                    _optional_text(error_category),
                    _optional_text(error_message),
                    detail_json,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError(
                    "validation observation insert did not return a row id"
                )
            return cursor.lastrowid

    def get_run(self, run_id: str) -> ReportRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM report_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return run_from_row(row)

    def latest(
        self,
        subject_kind: str,
        subject_id: str,
    ) -> Optional[ValidationObservation]:
        rows = self._latest_query(
            subject_kind=subject_kind,
            subject_id=subject_id,
        )
        return rows[0] if rows else None

    def current(
        self,
        *,
        subject_kind: Optional[str] = None,
    ) -> tuple[ValidationObservation, ...]:
        return self._latest_query(subject_kind=subject_kind)

    def as_of(
        self,
        timestamp: str,
        *,
        subject_kind: Optional[str] = None,
    ) -> tuple[ValidationObservation, ...]:
        return self._latest_query(
            subject_kind=subject_kind,
            observed_at_or_before=_timestamp(timestamp),
        )

    def observations_for_run(
        self,
        run_id: str,
    ) -> tuple[ValidationObservation, ...]:
        with self._connect() as connection:
            return observations_for_run(connection, run_id)

    def observations_for_subject(
        self,
        subject_kind: str,
        subject_id: str,
    ) -> tuple[ValidationObservation, ...]:
        """Return all immutable observations for one subject, newest first."""
        with self._connect() as connection:
            return observations_for_subject(
                connection,
                subject_kind=subject_kind,
                subject_id=subject_id,
            )

    def _latest_query(
        self,
        *,
        subject_kind: Optional[str] = None,
        subject_id: Optional[str] = None,
        observed_at_or_before: Optional[str] = None,
    ) -> tuple[ValidationObservation, ...]:
        if subject_kind is not None and subject_kind not in _SUBJECT_KINDS:
            raise ValueError(f"不支持的报告对象类型: {subject_kind}")
        normalized_subject_id = (
            _required_text(subject_id, "subject_id") if subject_id is not None else None
        )
        with self._connect() as connection:
            return latest_observations(
                connection,
                subject_kind=subject_kind,
                subject_id=normalized_subject_id,
                observed_at_or_before=observed_at_or_before,
            )

    def _connect(self) -> sqlite3.Connection:
        return connect_report_database(self.path)


def _validate_observation(subject_kind: str, status: str) -> None:
    if subject_kind not in _SUBJECT_KINDS:
        raise ValueError(f"不支持的报告对象类型: {subject_kind}")
    if status not in _OBSERVATION_STATUSES:
        raise ValueError(f"不支持的验证观测状态: {status}")


def _timestamp(value: Optional[str]) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    normalized = value.strip()
    if not normalized:
        raise ValueError("时间戳不能为空")
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("时间戳必须包含时区")
    return parsed.astimezone(timezone.utc).isoformat()


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    return normalized


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_latency(value: Optional[float], field_name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{field_name} 不能为负数")
