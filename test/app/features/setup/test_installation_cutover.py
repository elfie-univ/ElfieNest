"""Card 18 successful legacy Setup state projections."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.features.setup.progress import get_setup_progress
from app.infrastructure.persistence.store import get_db, init_db


@pytest.mark.parametrize(
    ("current_step", "expected_step"),
    (
        (1, "not_started"),
        (2, "owner"),
        (3, "providers"),
        (4, "nest"),
        (5, "food"),
    ),
)
def test_cutover_maps_legacy_steps_and_preserves_task_state(
    tmp_path: Path,
    current_step: int,
    expected_step: str,
) -> None:
    # Given: one legacy milestone/task snapshot in an explicit temporary root.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            """
            UPDATE setup_progress
            SET current_step = ?, active_task_step = 2,
                active_task_key = 'ollama_install', task_state = 'failed',
                task_progress = 0, last_error = 'retry me'
            WHERE singleton_id = 1
            """,
            (current_step,),
        )
        connection.commit()

    # When: the repository is opened for the first time after Card 18.
    get_setup_progress(db_path)

    # Then: the target singleton has the exact step/device/task projection.
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM local_installations WHERE installation_id = 'local'"
        ).fetchone()
    assert row is not None
    assert row["setup_step"] == expected_step
    assert row["device_name"] == "local"
    assert row["platform"] == sys.platform
    assert row["machine_id_hash"] is None
    assert tuple(
        row[key]
        for key in (
            "active_task_step",
            "active_task_key",
            "task_state",
            "task_progress",
            "last_error",
        )
    ) == (2, "ollama_install", "failed", 0, "retry me")


def test_completed_at_overrides_legacy_step_without_inventing_timestamps(
    tmp_path: Path,
) -> None:
    # Given: a completed legacy record whose old step counter is stale.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            """
            UPDATE setup_progress
            SET current_step = 2, owner_completed_at = '2026-07-01T01:00:00Z',
                nest_completed_at = '2026-07-01T03:00:00Z',
                completed_at = '2026-07-01T05:00:00Z'
            WHERE singleton_id = 1
            """
        )
        connection.commit()

    # When: cutover copies the record.
    progress = get_setup_progress(db_path)

    # Then: completion wins and unavailable provider/food times stay NULL.
    with get_db(db_path) as connection:
        row = connection.execute(
            """
            SELECT setup_state, setup_step, owner_completed_at,
                   providers_completed_at, nest_completed_at,
                   food_completed_at, completed_at
            FROM local_installations WHERE installation_id = 'local'
            """
        ).fetchone()
    assert progress.complete is True
    assert row is not None
    assert tuple(row) == (
        "completed",
        "food",
        "2026-07-01T01:00:00Z",
        None,
        "2026-07-01T03:00:00Z",
        None,
        "2026-07-01T05:00:00Z",
    )
