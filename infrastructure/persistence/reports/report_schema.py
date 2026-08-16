"""SQLite schema and connection policy for model/food/tool reports."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 4


def connect_report_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_report_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _secure(path.parent, 0o700)
    with connect_report_database(path) as connection:
        connection.executescript(_BASE_SCHEMA)
        current = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        if current == 1:
            _migrate_subject_kinds(connection)
        # Reinstall this trigger so databases created before the retention
        # policy get the same guarded maintenance path as fresh databases.
        connection.execute(
            "DROP TRIGGER IF EXISTS validation_observations_no_delete"
        )
        connection.executescript(_IMMUTABILITY_TRIGGERS)
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (version, applied_at)
            VALUES (?, ?)
            """,
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
    _secure(path, 0o600)


_BASE_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS validation_rollups (
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    observation_count INTEGER NOT NULL CHECK(observation_count > 0),
    passed_count INTEGER NOT NULL CHECK(passed_count >= 0),
    failed_count INTEGER NOT NULL CHECK(failed_count >= 0),
    warning_count INTEGER NOT NULL CHECK(warning_count >= 0),
    skipped_count INTEGER NOT NULL CHECK(skipped_count >= 0),
    average_latency_ms REAL,
    min_latency_ms REAL,
    max_latency_ms REAL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(subject_kind, subject_id, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_validation_rollup_subject_time
ON validation_rollups(subject_kind, subject_id, bucket_start DESC);

CREATE TABLE IF NOT EXISTS report_maintenance (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    retention_enabled INTEGER NOT NULL DEFAULT 0 CHECK(retention_enabled IN (0,1))
);

INSERT OR IGNORE INTO report_maintenance (id, retention_enabled) VALUES (1, 0);

CREATE TABLE IF NOT EXISTS validation_leases (
    lease_key TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_validation_lease_expiry
ON validation_leases (expires_at);
"""

_IMMUTABILITY_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS validation_observations_no_update
BEFORE UPDATE ON validation_observations
BEGIN
    SELECT RAISE(ABORT, 'validation observations are immutable');
END;

CREATE TRIGGER IF NOT EXISTS validation_observations_no_delete
BEFORE DELETE ON validation_observations
WHEN COALESCE((SELECT retention_enabled FROM report_maintenance WHERE id = 1), 0) = 0
BEGIN
    SELECT RAISE(ABORT, 'validation observations are immutable');
END;

CREATE TRIGGER IF NOT EXISTS report_runs_terminal_no_update
BEFORE UPDATE OF status, finished_at ON report_runs
WHEN OLD.status <> 'running'
  OR OLD.finished_at IS NOT NULL
  OR NEW.status NOT IN ('complete', 'partial', 'failed')
  OR NEW.finished_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'report run transition is invalid');
END;
"""


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


def _secure(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass
