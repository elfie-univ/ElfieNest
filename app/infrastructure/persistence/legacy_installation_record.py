"""Typed read projection for the legacy local installation singleton."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyInstallationRecord:
    """Complete legacy singleton payload required by the one-time cutover."""

    __slots__ = (
        "progress_schema_version",
        "current_step",
        "owner_user_id",
        "owner_completed_at",
        "ollama_decision",
        "ollama_endpoint",
        "nest_completed_at",
        "model_decision",
        "model_reference",
        "active_task_step",
        "active_task_key",
        "task_state",
        "task_progress",
        "last_error",
        "completed_at",
        "updated_at",
    )

    progress_schema_version: int
    current_step: int
    owner_user_id: int | None
    owner_completed_at: str | None
    ollama_decision: str | None
    ollama_endpoint: str | None
    nest_completed_at: str | None
    model_decision: str | None
    model_reference: str | None
    active_task_step: int | None
    active_task_key: str | None
    task_state: str
    task_progress: int
    last_error: str | None
    completed_at: str | None
    updated_at: str


def legacy_installation_record_from_row(
    row: sqlite3.Row,
) -> LegacyInstallationRecord:
    """Parse one repository-owned SQLite row into the immutable projection."""
    return LegacyInstallationRecord(
        progress_schema_version=int(row["progress_schema_version"]),
        current_step=int(row["current_step"]),
        owner_user_id=(
            int(row["owner_user_id"])
            if row["owner_user_id"] is not None
            else None
        ),
        owner_completed_at=(
            str(row["owner_completed_at"])
            if row["owner_completed_at"] is not None
            else None
        ),
        ollama_decision=(
            str(row["ollama_decision"])
            if row["ollama_decision"] is not None
            else None
        ),
        ollama_endpoint=(
            str(row["ollama_endpoint"])
            if row["ollama_endpoint"] is not None
            else None
        ),
        nest_completed_at=(
            str(row["nest_completed_at"])
            if row["nest_completed_at"] is not None
            else None
        ),
        model_reference=(
            str(row["model_reference"])
            if row["model_reference"] is not None
            else None
        ),
        model_decision=(
            str(row["model_decision"])
            if row["model_decision"] is not None
            else None
        ),
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
        updated_at=str(row["updated_at"]),
    )
