"""Read-only bounded projection owned by the Activity system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.activity.system import (
    ActivityRecord,
    ActivityState,
    ActivityStepKind,
    ActivityStorePort,
)
from elfie.message_types import (
    ActivityId,
    ErrorInfo,
    EventId,
    FrozenContractModel,
    UTCDateTime,
)

_ActivityText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=1024, pattern=r".*\S.*"),
]
_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]


class ActivityContextItem(FrozenContractModel):
    """Bounded projection of one committed cross-turn Activity."""

    activity_id: ActivityId
    revision: _Revision
    state: ActivityState
    goal: _ActivityText
    success_criteria: _ActivityText
    deadline: UTCDateTime
    updated_at: UTCDateTime
    next_wakeup_at: Optional[UTCDateTime] = None
    current_step_id: Optional[EventId] = None
    current_step_kind: Optional[ActivityStepKind] = None
    current_step_operation: Optional[_ActivityText] = None
    last_error: Optional[ErrorInfo] = None


class ActivityContext(FrozenContractModel):
    """Versioned Activity snapshot captured at one Brain Turn cutoff."""

    revision: _Revision
    captured_at: UTCDateTime
    items: Tuple[ActivityContextItem, ...]
    truncated: bool = False
    unknown_fields: Tuple[_NonBlankText, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"

    @classmethod
    def unknown(cls) -> ActivityContext:
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            items=(),
            unknown_fields=("activities",),
            freshness="unknown",
        )

    @model_validator(mode="after")
    def validate_snapshot(self) -> ActivityContext:
        activity_ids = tuple(str(item.activity_id) for item in self.items)
        if len(set(activity_ids)) != len(activity_ids):
            raise PydanticCustomError(
                "activity_context_identity",
                "Activity context IDs must be unique",
            )
        if any(item.updated_at > self.captured_at for item in self.items):
            raise PydanticCustomError(
                "activity_context_captured_at",
                "Activity context items cannot be newer than its cutoff",
            )
        return self


class ActivityContextReader:
    """Project Activity owner state at one immutable Turn cutoff."""

    def __init__(
        self,
        store: ActivityStorePort | None,
        *,
        capacity: int = 16,
    ) -> None:
        if capacity < 1:
            raise ValueError("activities capacity must be positive")
        self._store = store
        self._capacity = capacity

    def read(self, captured_at: UTCDateTime) -> ActivityContext:
        if self._store is None:
            return ActivityContext.unknown().model_copy(
                update={"captured_at": captured_at}
            )
        records = self._store.list()
        visible = tuple(
            record for record in records if record.updated_at <= captured_at
        )
        has_newer = any(record.updated_at > captured_at for record in records)
        active = {
            ActivityState.VALIDATED,
            ActivityState.WAITING,
            ActivityState.RUNNING,
            ActivityState.PAUSED,
        }
        ordered = tuple(
            sorted(
                visible,
                key=lambda record: (
                    0 if record.state in active else 1,
                    -record.updated_at.timestamp(),
                    str(record.activity_id),
                ),
            )
        )
        selected = ordered[: self._capacity]
        return ActivityContext(
            revision=max((record.revision for record in visible), default=0),
            captured_at=captured_at,
            items=tuple(self._item(record) for record in selected),
            truncated=len(ordered) > self._capacity,
            unknown_fields=("newer_activity_state",) if has_newer else (),
            freshness="stale" if has_newer else "current",
        )

    @staticmethod
    def _item(record: ActivityRecord) -> ActivityContextItem:
        current_step = next(
            (
                step
                for step in record.draft.steps
                if step.step_id == record.current_step_id
            ),
            None,
        )
        return ActivityContextItem(
            activity_id=record.activity_id,
            revision=record.revision,
            state=record.state,
            goal=record.draft.goal,
            success_criteria=record.draft.success_criteria,
            deadline=record.draft.deadline,
            updated_at=record.updated_at,
            next_wakeup_at=record.next_wakeup_at,
            current_step_id=record.current_step_id,
            current_step_kind=current_step.kind if current_step is not None else None,
            current_step_operation=(
                current_step.operation if current_step is not None else None
            ),
            last_error=record.last_error,
        )


__all__ = ("ActivityContext", "ActivityContextItem", "ActivityContextReader")
