"""Append-oriented SQLite repository for AI Runtime reports."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ai_runtime.storage.data_home import get_report_database_path

SCHEMA_VERSION = 2
_RUN_STATUSES = frozenset({"running", "complete", "partial", "failed"})
_SUBJECT_KINDS = frozenset({"provider", "model", "food", "fallback", "tool", "runtime"})
_OBSERVATION_STATUSES = frozenset({"passed", "failed", "warning", "skipped"})


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


class ReportRepository:
    """The sole writer and query boundary for Runtime validation evidence."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or get_report_database_path()
        self._initialize()

    def start_run(
        self,
        *,
        scope: str,
        trigger: str,
        started_at: Optional[str] = None,
    ) -> str:
        normalized_scope = _required_text(scope, "scope")
        normalized_trigger = _required_text(trigger, "trigger")
        timestamp = _timestamp(started_at)
        run_id = f"run_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO report_runs (
                    run_id, scope, trigger, started_at, status
                ) VALUES (?, ?, ?, ?, 'running')
                """,
                (run_id, normalized_scope, normalized_trigger, timestamp),
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
        timestamp = _timestamp(finished_at)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE report_runs
                SET status = ?, finished_at = ?
                WHERE run_id = ? AND status = 'running'
                """,
                (status, timestamp, run_id),
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
        if subject_kind not in _SUBJECT_KINDS:
            raise ValueError(f"不支持的报告对象类型: {subject_kind}")
        if status not in _OBSERVATION_STATUSES:
            raise ValueError(f"不支持的验证观测状态: {status}")
        normalized_subject_id = _required_text(subject_id, "subject_id")
        timestamp = _timestamp(observed_at)
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
                "SELECT 1 FROM report_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ValueError(f"报告运行不存在: {run_id}")
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
                    normalized_subject_id,
                    timestamp,
                    status,
                    latency_ms,
                    time_to_first_token_ms,
                    _optional_text(error_category),
                    _optional_text(error_message),
                    detail_json,
                ),
            )
            return int(cursor.lastrowid)

    def get_run(self, run_id: str) -> ReportRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM report_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _run_from_row(row)

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
            rows = connection.execute(
                """
                SELECT * FROM validation_observations
                WHERE run_id = ?
                ORDER BY observation_id
                """,
                (run_id,),
            ).fetchall()
        return tuple(_observation_from_row(row) for row in rows)

    def _latest_query(
        self,
        *,
        subject_kind: Optional[str] = None,
        subject_id: Optional[str] = None,
        observed_at_or_before: Optional[str] = None,
    ) -> tuple[ValidationObservation, ...]:
        if subject_kind is not None and subject_kind not in _SUBJECT_KINDS:
            raise ValueError(f"不支持的报告对象类型: {subject_kind}")
        filters = []
        parameters: list[Any] = []
        if subject_kind is not None:
            filters.append("candidate.subject_kind = ?")
            parameters.append(subject_kind)
        if subject_id is not None:
            filters.append("candidate.subject_id = ?")
            parameters.append(_required_text(subject_id, "subject_id"))
        if observed_at_or_before is not None:
            filters.append("candidate.observed_at <= ?")
            parameters.append(observed_at_or_before)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        later_time_filter = ""
        if observed_at_or_before is not None:
            later_time_filter = "AND later.observed_at <= ?"
            parameters.append(observed_at_or_before)
        sql = f"""
            SELECT candidate.*
            FROM validation_observations AS candidate
            {where}
            AND NOT EXISTS (
                SELECT 1
                FROM validation_observations AS later
                WHERE later.subject_kind = candidate.subject_kind
                  AND later.subject_id = candidate.subject_id
                  {later_time_filter}
                  AND (
                    later.observed_at > candidate.observed_at
                    OR (
                        later.observed_at = candidate.observed_at
                        AND later.observation_id > candidate.observation_id
                    )
                  )
            )
            ORDER BY candidate.subject_kind, candidate.subject_id
        """
        if not filters:
            sql = sql.replace(
                "\n            AND NOT EXISTS", "\n            WHERE NOT EXISTS", 1
            )
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(_observation_from_row(row) for row in rows)

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _secure(self.path.parent, 0o700)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS report_runs (
                    run_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL
                        CHECK (status IN ('running', 'complete', 'partial', 'failed'))
                );

                CREATE TABLE IF NOT EXISTS validation_observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES report_runs(run_id),
                    subject_kind TEXT NOT NULL
                        CHECK (subject_kind IN (
                            'provider', 'model', 'food', 'fallback', 'tool', 'runtime'
                        )),
                    subject_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('passed', 'failed', 'warning', 'skipped')),
                    latency_ms REAL,
                    time_to_first_token_ms REAL,
                    error_category TEXT,
                    error_message TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_validation_subject_time
                ON validation_observations (
                    subject_kind, subject_id, observed_at DESC, observation_id DESC
                );

                CREATE INDEX IF NOT EXISTS idx_validation_run
                ON validation_observations (run_id, observation_id);
                """
            )
            current = connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
            if current == 1:
                _migrate_subject_kinds(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, applied_at)
                VALUES (?, ?)
                """,
                (SCHEMA_VERSION, _timestamp(None)),
            )
        _secure(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection


def _run_from_row(row: sqlite3.Row) -> ReportRun:
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


def _migrate_subject_kinds(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        ALTER TABLE validation_observations RENAME TO validation_observations_v1;

        CREATE TABLE validation_observations (
            observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES report_runs(run_id),
            subject_kind TEXT NOT NULL
                CHECK (subject_kind IN (
                    'provider', 'model', 'food', 'fallback', 'tool', 'runtime'
                )),
            subject_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('passed', 'failed', 'warning', 'skipped')),
            latency_ms REAL,
            time_to_first_token_ms REAL,
            error_category TEXT,
            error_message TEXT,
            details_json TEXT NOT NULL DEFAULT '{}'
        );

        INSERT INTO validation_observations
        SELECT * FROM validation_observations_v1;
        DROP TABLE validation_observations_v1;

        CREATE INDEX idx_validation_subject_time
        ON validation_observations (
            subject_kind, subject_id, observed_at DESC, observation_id DESC
        );
        CREATE INDEX idx_validation_run
        ON validation_observations (run_id, observation_id);
        """
    )


def _observation_from_row(row: sqlite3.Row) -> ValidationObservation:
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


def _timestamp(value: Optional[str]) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    normalized = value.strip()
    if not normalized:
        raise ValueError("时间戳不能为空")
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("时间戳必须包含时区")
    return normalized


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


def _secure(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass
