"""Typed projection of the final local installation row."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final

_STEP_ORDER: Final[tuple[str, ...]] = (
    "not_started",
    "owner",
    "providers",
    "nest",
    "food",
)


@dataclass(frozen=True)
class InstallationRecord:
    """Fields required to project and resume the five-step Setup wizard."""

    __slots__ = (
        "owner_user_id",
        "setup_state",
        "setup_step",
        "active_task_step",
        "active_task_key",
        "task_state",
        "task_progress",
        "last_error",
        "completed_at",
    )

    owner_user_id: int | None
    setup_state: str
    setup_step: str
    active_task_step: int | None
    active_task_key: str | None
    task_state: str
    task_progress: int
    last_error: str | None
    completed_at: str | None


def installation_record_from_row(row: sqlite3.Row) -> InstallationRecord:
    """Parse one final SQLite row into the immutable Setup projection."""
    return InstallationRecord(
        owner_user_id=(
            int(row["owner_user_id"])
            if row["owner_user_id"] is not None
            else None
        ),
        setup_state=str(row["setup_state"]),
        setup_step=str(row["setup_step"]),
        active_task_step=(
            int(row["active_task_step"])
            if row["active_task_step"] is not None
            else None
        ),
        active_task_key=(
            str(row["active_task_key"])
            if row["active_task_key"] is not None
            else None
        ),
        task_state=str(row["task_state"]),
        task_progress=int(row["task_progress"]),
        last_error=str(row["last_error"]) if row["last_error"] else None,
        completed_at=(
            str(row["completed_at"]) if row["completed_at"] is not None else None
        ),
    )


def installation_step_states(record: InstallationRecord) -> tuple[bool, ...]:
    """Return completion flags in the public wizard's fixed five-step order."""
    if record.setup_state == "completed":
        return (True, True, True, True, True)
    completed_index = _STEP_ORDER.index(record.setup_step)
    return tuple(step <= completed_index for step in range(1, 6))
