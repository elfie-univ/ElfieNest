"""SQLite schema and connection policy for model/food/tool reports."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2


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
"""

_IMMUTABILITY_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS validation_observations_no_update
BEFORE UPDATE ON validation_observations
BEGIN
    SELECT RAISE(ABORT, 'validation observations are immutable');
END;

CREATE TRIGGER IF NOT EXISTS validation_observations_no_delete
BEFORE DELETE ON validation_observations
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
