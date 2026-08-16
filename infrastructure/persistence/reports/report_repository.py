"""Append-oriented SQLite repository for model/food/tool reports."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Optional

from pydantic import JsonValue

from infrastructure.models.report_records import (
    ReportRun,
    ValidationObservation,
    ValidationRollup,
)
from infrastructure.persistence.layout.data_home import get_report_database_path
from infrastructure.persistence.reports.report_queries import (
    latest_observations,
    observations_for_run,
    observations_for_subject,
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

    def try_acquire_validation_lease(
        self,
        lease_key: str,
        owner_id: str,
        *,
        lease_seconds: int,
        now: Optional[str] = None,
    ) -> bool:
        """Atomically acquire or renew one cross-process validation lease."""
        key = _required_text(lease_key, "lease_key")
        owner = _required_text(owner_id, "owner_id")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须大于 0")
        acquired_at = _timestamp(now)
        acquired_datetime = datetime.fromisoformat(acquired_at)
        expires_at = (
            (acquired_datetime + timedelta(seconds=lease_seconds))
            .astimezone(timezone.utc)
            .isoformat()
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT owner_id, expires_at FROM validation_leases WHERE lease_key = ?",
                (key,),
            ).fetchone()
            if (
                current is not None
                and current["owner_id"] != owner
                and str(current["expires_at"]) > acquired_at
            ):
                return False
            connection.execute(
                """
                INSERT INTO validation_leases (
                    lease_key, owner_id, acquired_at, expires_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(lease_key) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    acquired_at = excluded.acquired_at,
                    expires_at = excluded.expires_at
                """,
                (key, owner, acquired_at, expires_at),
            )
            return True

    def release_validation_lease(self, lease_key: str, owner_id: str) -> bool:
        key = _required_text(lease_key, "lease_key")
        owner = _required_text(owner_id, "owner_id")
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM validation_leases WHERE lease_key = ? AND owner_id = ?",
                (key, owner),
            )
            return cursor.rowcount == 1

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
        details: Optional[Mapping[str, JsonValue]] = None,
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

    def compact_observations(self, before: str) -> int:
        """Roll up and remove old raw observations in one guarded transaction.

        Raw observations remain immutable to ordinary callers.  Retention is
        the only controlled deletion path: it first stores daily, content-free
        aggregates, then removes observations from finished runs while holding
        the SQLite write lock.  The method returns the number of raw rows
        removed.
        """
        cutoff = _timestamp(before)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE report_maintenance SET retention_enabled = 1 WHERE id = 1"
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO validation_rollups (
                    subject_kind, subject_id, bucket_start, observation_count,
                    passed_count, failed_count, warning_count, skipped_count,
                    average_latency_ms, min_latency_ms, max_latency_ms,
                    first_observed_at, last_observed_at, created_at
                )
                SELECT
                    observation.subject_kind,
                    observation.subject_id,
                    substr(observation.observed_at, 1, 10)
                        || 'T00:00:00+00:00',
                    COUNT(*),
                    SUM(CASE WHEN observation.status = 'passed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN observation.status = 'failed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN observation.status = 'warning' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN observation.status = 'skipped' THEN 1 ELSE 0 END),
                    AVG(observation.latency_ms),
                    MIN(observation.latency_ms),
                    MAX(observation.latency_ms),
                    MIN(observation.observed_at),
                    MAX(observation.observed_at),
                    ?
                FROM validation_observations AS observation
                JOIN report_runs AS run ON run.run_id = observation.run_id
                WHERE observation.observed_at < ?
                  AND run.status <> 'running'
                GROUP BY observation.subject_kind, observation.subject_id,
                         substr(observation.observed_at, 1, 10)
                """,
                (_timestamp(None), cutoff),
            )
            removed = connection.execute(
                """
                DELETE FROM validation_observations
                WHERE observed_at < ?
                  AND run_id IN (
                      SELECT run_id FROM report_runs WHERE status <> 'running'
                  )
                """,
                (cutoff,),
            ).rowcount
            connection.execute(
                "UPDATE report_maintenance SET retention_enabled = 0 WHERE id = 1"
            )
            connection.execute(
                """
                DELETE FROM report_runs
                WHERE status <> 'running'
                  AND finished_at IS NOT NULL
                  AND finished_at < ?
                  AND NOT EXISTS (
                      SELECT 1 FROM validation_observations
                      WHERE validation_observations.run_id = report_runs.run_id
                  )
                """,
                (cutoff,),
            )
            return int(removed)

    def validation_rollups(
        self,
        *,
        subject_kind: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[ValidationRollup, ...]:
        """Read retained daily aggregates without exposing raw content."""
        filters: list[str] = []
        parameters: list[str] = []
        if subject_kind is not None:
            filters.append("subject_kind = ?")
            parameters.append(subject_kind)
        if subject_id is not None:
            filters.append("subject_id = ?")
            parameters.append(subject_id)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT subject_kind, subject_id, bucket_start,
                       observation_count, passed_count, failed_count,
                       warning_count, skipped_count, average_latency_ms,
                       min_latency_ms, max_latency_ms, first_observed_at,
                       last_observed_at
                FROM validation_rollups
                {where}
                ORDER BY subject_kind, subject_id, bucket_start
                """,
                parameters,
            ).fetchall()
        return tuple(
            ValidationRollup(
                subject_kind=str(row["subject_kind"]),
                subject_id=str(row["subject_id"]),
                bucket_start=str(row["bucket_start"]),
                observation_count=int(row["observation_count"]),
                passed_count=int(row["passed_count"]),
                failed_count=int(row["failed_count"]),
                warning_count=int(row["warning_count"]),
                skipped_count=int(row["skipped_count"]),
                average_latency_ms=(
                    None
                    if row["average_latency_ms"] is None
                    else float(row["average_latency_ms"])
                ),
                min_latency_ms=(
                    None
                    if row["min_latency_ms"] is None
                    else float(row["min_latency_ms"])
                ),
                max_latency_ms=(
                    None
                    if row["max_latency_ms"] is None
                    else float(row["max_latency_ms"])
                ),
                first_observed_at=str(row["first_observed_at"]),
                last_observed_at=str(row["last_observed_at"]),
            )
            for row in rows
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


def run_from_row(row: sqlite3.Row) -> ReportRun:
    """Decode a SQLite row at the persistence boundary."""
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
