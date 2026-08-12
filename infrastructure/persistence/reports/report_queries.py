"""Read-only SQLite projections for model/food/tool validation reports."""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from infrastructure.persistence.reports.report_records import (
    ValidationObservation,
    observation_from_row,
)


def latest_observations(
    connection: sqlite3.Connection,
    *,
    subject_kind: Optional[str] = None,
    subject_id: Optional[str] = None,
    observed_at_or_before: Optional[str] = None,
) -> tuple[ValidationObservation, ...]:
    filters = []
    parameters: list[Any] = []
    if subject_kind is not None:
        filters.append("candidate.subject_kind = ?")
        parameters.append(subject_kind)
    if subject_id is not None:
        filters.append("candidate.subject_id = ?")
        parameters.append(subject_id)
    if observed_at_or_before is not None:
        filters.append("candidate.observed_at <= ?")
        parameters.append(observed_at_or_before)
    where = f"WHERE {' AND '.join(filters)}" if filters else "WHERE 1 = 1"
    later_time_filter = ""
    if observed_at_or_before is not None:
        later_time_filter = "AND later.observed_at <= ?"
        parameters.append(observed_at_or_before)
    rows = connection.execute(
        f"""
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
        """,
        parameters,
    ).fetchall()
    return tuple(observation_from_row(row) for row in rows)


def observations_for_run(
    connection: sqlite3.Connection,
    run_id: str,
) -> tuple[ValidationObservation, ...]:
    rows = connection.execute(
        """
        SELECT * FROM validation_observations
        WHERE run_id = ?
        ORDER BY observation_id
        """,
        (run_id,),
    ).fetchall()
    return tuple(observation_from_row(row) for row in rows)


def observations_for_subject(
    connection: sqlite3.Connection,
    *,
    subject_kind: str,
    subject_id: str,
) -> tuple[ValidationObservation, ...]:
    """Return immutable observations for one subject, newest first."""
    rows = connection.execute(
        """
        SELECT * FROM validation_observations
        WHERE subject_kind = ? AND subject_id = ?
        ORDER BY observed_at DESC, observation_id DESC
        """,
        (subject_kind, subject_id),
    ).fetchall()
    return tuple(observation_from_row(row) for row in rows)
