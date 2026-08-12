"""SQLite Adapter for one Elfie's semantic Persistent Activity Port."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Final, Optional

from elfie.brain.activity import (
    ActivityDraft,
    ActivityPreflightResult,
    ActivityPreflightStatus,
    ActivityRecord,
    ActivityState,
    ActivityStateEvent,
    ActivityStepProgress,
    ActivityStorePort,
    transition_activity,
)
from elfie.message_types import ActivityId, ErrorInfo, EventId, UTCDateTime
from infrastructure.persistence.nest_db.sqlite_connection import (
    UnsafeSQLitePathError,
    connect_app_sqlite,
)

_FINAL_FILENAME: Final = "activity.sqlite"


class ActivityStorePathError(Exception):
    """The Activity Adapter requires the final filename or test memory."""

    __slots__ = ("db_path",)

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"SQLite Activity Adapter requires {_FINAL_FILENAME}: {self.db_path}"


class ActivityStoreConflict(RuntimeError):
    """A stale revision or conflicting idempotency key was submitted."""


class SQLiteActivityStoreAdapter(ActivityStorePort):
    """Persist typed Activity records without exposing SQL to Brain."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = self._parse_path(db_path)
        try:
            self.conn = connect_app_sqlite(self._db_path, check_same_thread=False)
        except UnsafeSQLitePathError as error:
            raise ActivityStorePathError(str(db_path)) from error
        self._initialize_schema()

    @classmethod
    def in_memory(cls) -> SQLiteActivityStoreAdapter:
        """Create an isolated store for Brain and adapter tests."""
        return cls(":memory:")

    def __enter__(self) -> SQLiteActivityStoreAdapter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def close(self) -> None:
        self.conn.close()

    def preflight(
        self,
        draft: ActivityDraft,
        *,
        now: UTCDateTime,
    ) -> ActivityPreflightResult:
        """Validate time and idempotency without inserting or updating rows."""
        if draft.created_at > now:
            return ActivityPreflightResult(
                activity_id=draft.activity_id,
                status=ActivityPreflightStatus.REJECTED,
                checked_at=now,
                reasons=(
                    ErrorInfo(
                        code="activity_created_in_future",
                        message="Activity creation time cannot be in the future",
                    ),
                ),
            )
        if draft.deadline <= now:
            return ActivityPreflightResult(
                activity_id=draft.activity_id,
                status=ActivityPreflightStatus.REJECTED,
                checked_at=now,
                reasons=(
                    ErrorInfo(
                        code="activity_deadline_expired",
                        message="Activity deadline is not in the future",
                    ),
                ),
            )
        row = self.conn.execute(
            "SELECT activity_id, draft_json FROM activities WHERE idempotency_key=?",
            (draft.idempotency_key,),
        ).fetchone()
        if row is not None:
            existing = ActivityDraft.model_validate_json(row["draft_json"])
            if existing != draft:
                return ActivityPreflightResult(
                    activity_id=draft.activity_id,
                    status=ActivityPreflightStatus.REJECTED,
                    checked_at=now,
                    reasons=(
                        ErrorInfo(
                            code="activity_idempotency_conflict",
                            message="Activity idempotency key already belongs to another draft",
                        ),
                    ),
                )
        activity_row = self.conn.execute(
            "SELECT draft_json FROM activities WHERE activity_id=?",
            (str(draft.activity_id),),
        ).fetchone()
        if activity_row is not None:
            existing_activity = ActivityDraft.model_validate_json(
                activity_row["draft_json"]
            )
            if existing_activity != draft:
                return ActivityPreflightResult(
                    activity_id=draft.activity_id,
                    status=ActivityPreflightStatus.REJECTED,
                    checked_at=now,
                    reasons=(
                        ErrorInfo(
                            code="activity_id_conflict",
                            message="Activity ID already belongs to another draft",
                        ),
                    ),
                )
        return ActivityPreflightResult(
            activity_id=draft.activity_id,
            status=ActivityPreflightStatus.VALIDATED,
            checked_at=now,
        )

    def commit(
        self,
        draft: ActivityDraft,
        *,
        preflight: ActivityPreflightResult,
    ) -> ActivityRecord:
        """Insert one validated draft or return its idempotent existing record."""
        if preflight.activity_id != draft.activity_id:
            raise ActivityStoreConflict("Activity Preflight belongs to another draft")
        if preflight.status is not ActivityPreflightStatus.VALIDATED:
            raise ActivityStoreConflict("only a validated Activity draft may commit")
        existing_row = self.conn.execute(
            "SELECT * FROM activities WHERE idempotency_key=?",
            (draft.idempotency_key,),
        ).fetchone()
        if existing_row is not None:
            existing = self._decode(existing_row)
            if existing.draft != draft:
                raise ActivityStoreConflict("Activity idempotency key conflict")
            return existing

        initial_state = (
            ActivityState.WAITING
            if draft.wake_at is not None
            else ActivityState.RUNNING
        )
        record = ActivityRecord(
            activity_id=draft.activity_id,
            revision=0,
            state=initial_state,
            draft=draft,
            created_at=draft.created_at,
            updated_at=draft.created_at,
            next_wakeup_at=draft.wake_at,
            current_step_id=None
            if initial_state is ActivityState.WAITING
            else draft.steps[0].step_id,
            progress=tuple(
                ActivityStepProgress(step_id=step.step_id) for step in draft.steps
            ),
        )
        self.conn.execute(
            """INSERT INTO activities (
                   activity_id, idempotency_key, revision, state, draft_json,
                   created_at, updated_at, next_wakeup_at, current_step_id,
                   progress_json, last_error_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._encode_values(record),
        )
        self.conn.commit()
        return record

    def get(self, activity_id: ActivityId) -> Optional[ActivityRecord]:
        row = self.conn.execute(
            "SELECT * FROM activities WHERE activity_id=?",
            (str(activity_id),),
        ).fetchone()
        return None if row is None else self._decode(row)

    def list(self) -> tuple[ActivityRecord, ...]:
        rows = self.conn.execute(
            "SELECT * FROM activities ORDER BY updated_at, activity_id"
        ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def transition(
        self,
        activity_id: ActivityId,
        *,
        expected_revision: int,
        target: ActivityState,
        now: UTCDateTime,
        reason: Optional[str] = None,
        next_wakeup_at: Optional[UTCDateTime] = None,
    ) -> ActivityStateEvent:
        """Version-check, apply, and persist one pure lifecycle transition."""
        current = self.get(activity_id)
        if current is None:
            raise ActivityStoreConflict(f"Activity not found: {activity_id}")
        if current.revision != expected_revision:
            raise ActivityStoreConflict(
                f"Activity revision conflict: {current.revision} != {expected_revision}"
            )
        updated, event = transition_activity(
            current,
            target,
            now=now,
            reason=reason,
            next_wakeup_at=next_wakeup_at,
        )
        cursor = self.conn.execute(
            """UPDATE activities SET revision=?, state=?, updated_at=?,
                   next_wakeup_at=?, current_step_id=?, progress_json=?, last_error_json=?
               WHERE activity_id=? AND revision=?""",
            (
                updated.revision,
                updated.state.value,
                updated.updated_at.isoformat(),
                _serialize_datetime(updated.next_wakeup_at),
                _serialize_id(updated.current_step_id),
                json.dumps(
                    [item.model_dump(mode="json") for item in updated.progress],
                    ensure_ascii=False,
                ),
                _serialize_error(updated.last_error),
                str(activity_id),
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ActivityStoreConflict("Activity transition lost its revision race")
        self.conn.commit()
        return event

    def settle_step(
        self,
        activity_id: ActivityId,
        *,
        expected_revision: int,
        receipt_id: EventId,
        now: UTCDateTime,
        success: bool,
        reason: Optional[str] = None,
    ) -> ActivityStateEvent:
        """Settle one current external step from a real execution receipt."""
        current = self.get(activity_id)
        if current is None:
            raise ActivityStoreConflict(f"Activity not found: {activity_id}")
        if current.revision != expected_revision:
            raise ActivityStoreConflict(
                f"Activity revision conflict: {current.revision} != {expected_revision}"
            )
        target = ActivityState.COMPLETED if success else ActivityState.FAILED
        updated, event = transition_activity(
            current,
            target,
            now=now,
            reason=reason or f"step_receipt:{receipt_id}",
        )
        progress = tuple(
            item.model_copy(
                update={
                    "attempts": item.attempts + 1,
                    "last_receipt_id": receipt_id,
                }
            )
            if item.step_id == current.current_step_id
            else item
            for item in updated.progress
        )
        updated = updated.model_copy(update={"progress": progress})
        cursor = self.conn.execute(
            """UPDATE activities SET revision=?, state=?, updated_at=?,
                   next_wakeup_at=?, current_step_id=?, progress_json=?, last_error_json=?
               WHERE activity_id=? AND revision=?""",
            (
                updated.revision,
                updated.state.value,
                updated.updated_at.isoformat(),
                _serialize_datetime(updated.next_wakeup_at),
                _serialize_id(updated.current_step_id),
                json.dumps(
                    [item.model_dump(mode="json") for item in updated.progress],
                    ensure_ascii=False,
                ),
                _serialize_error(updated.last_error),
                str(activity_id),
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ActivityStoreConflict("Activity settlement lost its revision race")
        self.conn.commit()
        return event

    @staticmethod
    def _parse_path(db_path: str | Path) -> str | Path:
        if db_path == ":memory:":
            return ":memory:"
        path = Path(db_path)
        if path.name != _FINAL_FILENAME or path.is_symlink():
            raise ActivityStorePathError(str(db_path))
        return path

    def _initialize_schema(self) -> None:
        try:
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS activities (
                       activity_id TEXT PRIMARY KEY,
                       idempotency_key TEXT NOT NULL UNIQUE,
                       revision INTEGER NOT NULL CHECK (revision >= 0),
                       state TEXT NOT NULL,
                       draft_json TEXT NOT NULL,
                       created_at TEXT NOT NULL,
                       updated_at TEXT NOT NULL,
                       next_wakeup_at TEXT,
                       current_step_id TEXT,
                       progress_json TEXT NOT NULL,
                       last_error_json TEXT
                   )"""
            )
            self.conn.commit()
        except sqlite3.DatabaseError:
            self.conn.rollback()
            self.conn.close()
            raise

    @staticmethod
    def _encode_values(record: ActivityRecord) -> tuple[object, ...]:
        return (
            str(record.activity_id),
            record.draft.idempotency_key,
            record.revision,
            record.state.value,
            record.draft.model_dump_json(),
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
            _serialize_datetime(record.next_wakeup_at),
            _serialize_id(record.current_step_id),
            json.dumps(
                [item.model_dump(mode="json") for item in record.progress],
                ensure_ascii=False,
            ),
            _serialize_error(record.last_error),
        )

    @staticmethod
    def _decode(row: sqlite3.Row) -> ActivityRecord:
        progress = tuple(
            ActivityStepProgress.model_validate(item)
            for item in json.loads(row["progress_json"])
        )
        last_error_data = row["last_error_json"]
        created_at = _parse_datetime(row["created_at"])
        updated_at = _parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ActivityStoreConflict("Activity record has no creation timestamp")
        return ActivityRecord(
            activity_id=ActivityId(row["activity_id"]),
            revision=row["revision"],
            state=ActivityState(row["state"]),
            draft=ActivityDraft.model_validate_json(row["draft_json"]),
            created_at=created_at,
            updated_at=updated_at,
            next_wakeup_at=_parse_datetime(row["next_wakeup_at"]),
            current_step_id=row["current_step_id"],
            progress=progress,
            last_error=(
                ErrorInfo.model_validate(json.loads(last_error_data))
                if last_error_data
                else None
            ),
        )


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_id(value: object) -> str | None:
    return str(value) if value is not None else None


def _serialize_error(value: ErrorInfo | None) -> str | None:
    return value.model_dump_json() if value is not None else None


__all__ = (
    "ActivityStoreConflict",
    "ActivityStorePathError",
    "SQLiteActivityStoreAdapter",
)
