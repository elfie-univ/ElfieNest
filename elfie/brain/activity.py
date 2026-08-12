"""Typed Persistent Activity contracts and its pure lifecycle rules.

This module intentionally owns no database, scheduler, channel, or body adapter.
It defines the semantic boundary that those adapters will implement in later
Stage 5 slices.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum, unique
from threading import RLock
from typing import Literal, Optional, Protocol, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError
from typing_extensions import Annotated

from elfie.brain.perception_types import (
    ExternalExecutionDomain,
    InternalPayload,
    InternalSignal,
    PerceptionEvent,
    ResponseScope,
)
from elfie.message_types import (
    ActivityId,
    ActorId,
    ActorRef,
    CorrelationId,
    ElfieId,
    ErrorInfo,
    EventId,
    FrozenContractModel,
    MessageMeta,
    Priority,
    TraceId,
    UTCDateTime,
)

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=8192, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Ordinal = Annotated[int, Field(strict=True, ge=0)]
_RetryLimit = Annotated[int, Field(strict=True, ge=0, le=8)]
_Budget = Annotated[float, Field(strict=True, ge=0.0, le=100.0)]


@unique
class ActivityPreflightStatus(str, Enum):
    """Result of a side-effect-free Activity draft check."""

    VALIDATED = "validated"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"


@unique
class ActivityState(str, Enum):
    """Durable Activity lifecycle states."""

    VALIDATED = "validated"
    WAITING = "waiting"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@unique
class ActivityStepKind(str, Enum):
    """Closed execution domains for one Activity step."""

    COMMUNICATION = "communication"
    NERVOUS_SYSTEM = "nervous_system"
    INTERNAL = "internal"


class ActivityStep(FrozenContractModel):
    """One bounded step; external targets are copied as an explicit Scope."""

    step_id: EventId
    ordinal: _Ordinal
    kind: ActivityStepKind
    operation: _NonBlankText
    deadline: UTCDateTime
    scope: Optional[ResponseScope] = None
    retry_limit: _RetryLimit = 0

    @model_validator(mode="after")
    def validate_scope(self) -> ActivityStep:
        """Keep the declared step kind and target boundary aligned."""
        if self.kind is ActivityStepKind.COMMUNICATION:
            if (
                self.scope is None
                or self.scope.external_domain
                is not ExternalExecutionDomain.COMMUNICATION
            ):
                raise PydanticCustomError(
                    "activity_communication_scope",
                    "communication Activity steps require a communication scope",
                )
        elif self.kind is ActivityStepKind.NERVOUS_SYSTEM:
            if (
                self.scope is None
                or self.scope.external_domain
                is not ExternalExecutionDomain.NERVOUS_SYSTEM
            ):
                raise PydanticCustomError(
                    "activity_nervous_system_scope",
                    "nervous-system Activity steps require a body scope",
                )
        elif self.scope is not None:
            raise PydanticCustomError(
                "activity_internal_scope",
                "internal Activity steps cannot carry an external scope",
            )
        return self


class ActivityDraft(FrozenContractModel):
    """A non-persistent proposal submitted for synchronous Preflight."""

    schema_version: Literal[1] = 1
    activity_id: ActivityId
    goal: _NonBlankText
    success_criteria: _NonBlankText
    steps: Tuple[ActivityStep, ...] = Field(min_length=1)
    cause_event_ids: Tuple[EventId, ...] = Field(min_length=1)
    idempotency_key: _NonBlankText
    created_at: UTCDateTime
    deadline: UTCDateTime
    wake_at: Optional[UTCDateTime] = None
    estimated_budget: _Budget = 0.0

    @model_validator(mode="after")
    def validate_timeline(self) -> ActivityDraft:
        """Keep one Activity's causal IDs and temporal bounds coherent."""
        if self.deadline <= self.created_at:
            raise PydanticCustomError(
                "activity_deadline",
                "Activity deadline must be later than creation",
            )
        if self.wake_at is not None and self.wake_at > self.deadline:
            raise PydanticCustomError(
                "activity_wake_at",
                "Activity wake time cannot be later than its deadline",
            )
        step_ids = tuple(step.step_id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise PydanticCustomError(
                "activity_step_id",
                "Activity step IDs must be unique",
            )
        if len(set(self.cause_event_ids)) != len(self.cause_event_ids):
            raise PydanticCustomError(
                "activity_cause_event_id",
                "Activity cause event IDs must be unique",
            )
        if any(
            step.deadline <= self.created_at or step.deadline > self.deadline
            for step in self.steps
        ):
            raise PydanticCustomError(
                "activity_step_deadline",
                "Activity step deadlines must be inside the Activity window",
            )
        ordinals = tuple(step.ordinal for step in self.steps)
        if ordinals != tuple(sorted(ordinals)) or len(set(ordinals)) != len(ordinals):
            raise PydanticCustomError(
                "activity_step_order",
                "Activity step ordinals must be unique and ordered",
            )
        return self


class ActivityPreflightResult(FrozenContractModel):
    """Observable, side-effect-free result of checking one draft."""

    activity_id: ActivityId
    status: ActivityPreflightStatus
    checked_at: UTCDateTime
    reasons: Tuple[ErrorInfo, ...] = ()


class ActivityStepProgress(FrozenContractModel):
    """Durable progress for one step without embedding an adapter receipt."""

    step_id: EventId
    attempts: _Revision = 0
    last_receipt_id: Optional[EventId] = None


class ActivityRecord(FrozenContractModel):
    """Authoritative committed Activity state returned by a store Port."""

    activity_id: ActivityId
    revision: _Revision
    state: ActivityState
    draft: ActivityDraft
    created_at: UTCDateTime
    updated_at: UTCDateTime
    next_wakeup_at: Optional[UTCDateTime] = None
    current_step_id: Optional[EventId] = None
    progress: Tuple[ActivityStepProgress, ...] = ()
    last_error: Optional[ErrorInfo] = None

    @model_validator(mode="after")
    def validate_progress(self) -> ActivityRecord:
        """Ensure progress belongs to the committed draft."""
        known = {step.step_id for step in self.draft.steps}
        progress_ids = tuple(item.step_id for item in self.progress)
        if not set(progress_ids).issubset(known):
            raise PydanticCustomError(
                "activity_progress_step",
                "Activity progress references an unknown step",
            )
        if len(set(progress_ids)) != len(progress_ids):
            raise PydanticCustomError(
                "activity_progress_duplicate",
                "Activity progress step IDs must be unique",
            )
        if self.current_step_id is not None and self.current_step_id not in known:
            raise PydanticCustomError(
                "activity_current_step",
                "Activity current step must belong to the draft",
            )
        return self


class ActivityStateEvent(FrozenContractModel):
    """Typed state transition that can re-enter Brain as an Internal event."""

    activity_id: ActivityId
    revision: _Revision
    state: ActivityState
    occurred_at: UTCDateTime
    causation_event_ids: Tuple[EventId, ...] = Field(min_length=1)
    next_wakeup_at: Optional[UTCDateTime] = None
    reason: Optional[_NonBlankText] = None


def activity_scope_for_record(record: ActivityRecord) -> Optional[ResponseScope]:
    """Return the external scope of the step owned by the next Internal Turn."""
    step_id = record.current_step_id
    if step_id is None:
        return None
    step = next((item for item in record.draft.steps if item.step_id == step_id), None)
    return None if step is None else step.scope


def activity_state_event_to_perception(
    event: ActivityStateEvent,
    *,
    elfie_id: ElfieId,
    response_scope: Optional[ResponseScope] = None,
) -> PerceptionEvent:
    """Represent one Activity fact as a deduplicable typed Internal event."""
    event_id = EventId(
        f"activity-event:{event.activity_id}:{event.revision}:{event.state.value}"
    )
    occurred_at = event.occurred_at
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=event_id,
            elfie_id=elfie_id,
            source=ActorRef(
                actor_id=ActorId(f"{elfie_id}:activity"),
                source_kind="activity",
            ),
            occurred_at=occurred_at,
            received_at=occurred_at,
            trace_id=TraceId(f"activity:{event.activity_id}:{event.revision}"),
            causation_id=event.causation_event_ids[0],
            correlation_id=CorrelationId(str(event.activity_id)),
            priority=(
                Priority.HIGH
                if event.state in {ActivityState.FAILED, ActivityState.EXPIRED}
                else Priority.NORMAL
            ),
        ),
        payload=InternalPayload(
            type="internal",
            signal=InternalSignal.ACTIVITY,
            detail=json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
            response_scope=response_scope,
        ),
        salience=0.7,
    )


class ActivityTransitionError(ValueError):
    """Raised when a requested Activity state transition is not legal."""


_ALLOWED_TRANSITIONS = {
    ActivityState.VALIDATED: frozenset(
        {
            ActivityState.WAITING,
            ActivityState.RUNNING,
            ActivityState.CANCELLED,
            ActivityState.EXPIRED,
        }
    ),
    ActivityState.WAITING: frozenset(
        {
            ActivityState.RUNNING,
            ActivityState.PAUSED,
            ActivityState.CANCELLED,
            ActivityState.EXPIRED,
        }
    ),
    ActivityState.RUNNING: frozenset(
        {
            ActivityState.WAITING,
            ActivityState.PAUSED,
            ActivityState.COMPLETED,
            ActivityState.FAILED,
            ActivityState.CANCELLED,
            ActivityState.EXPIRED,
        }
    ),
    ActivityState.PAUSED: frozenset(
        {
            ActivityState.WAITING,
            ActivityState.RUNNING,
            ActivityState.CANCELLED,
            ActivityState.EXPIRED,
        }
    ),
    ActivityState.CANCELLED: frozenset(),
    ActivityState.COMPLETED: frozenset(),
    ActivityState.FAILED: frozenset(),
    ActivityState.EXPIRED: frozenset(),
}


def transition_activity(
    record: ActivityRecord,
    target: ActivityState,
    *,
    now: datetime,
    reason: Optional[str] = None,
    next_wakeup_at: Optional[datetime] = None,
) -> tuple[ActivityRecord, ActivityStateEvent]:
    """Apply one pure, version-incrementing Activity state transition."""
    if target not in _ALLOWED_TRANSITIONS[record.state]:
        raise ActivityTransitionError(
            f"illegal Activity transition: {record.state.value} -> {target.value}"
        )
    if now.tzinfo is None or now.utcoffset() is None:
        raise ActivityTransitionError("Activity transition time must be timezone-aware")
    if now < record.updated_at:
        raise ActivityTransitionError("Activity transition time cannot move backwards")
    if target is ActivityState.WAITING and next_wakeup_at is None:
        raise ActivityTransitionError("waiting Activity requires a wake time")
    if next_wakeup_at is not None and next_wakeup_at > record.draft.deadline:
        raise ActivityTransitionError("Activity wake time exceeds its deadline")
    updated = record.model_copy(
        update={
            "revision": record.revision + 1,
            "state": target,
            "updated_at": now,
            "next_wakeup_at": next_wakeup_at,
            "current_step_id": (
                record.current_step_id
                if target is not ActivityState.RUNNING
                else (record.current_step_id or record.draft.steps[0].step_id)
            ),
            "last_error": (
                ErrorInfo(code="activity_transition", message=reason)
                if target in {ActivityState.FAILED, ActivityState.EXPIRED}
                and reason is not None
                else None
            ),
        }
    )
    event = ActivityStateEvent(
        activity_id=record.activity_id,
        revision=updated.revision,
        state=target,
        occurred_at=now,
        causation_event_ids=record.draft.cause_event_ids,
        next_wakeup_at=next_wakeup_at,
        reason=reason,
    )
    return updated, event


class ActivityStorePort(Protocol):
    """Semantic Port for Activity preflight, commit, and state reads."""

    def preflight(
        self,
        draft: ActivityDraft,
        *,
        now: UTCDateTime,
    ) -> ActivityPreflightResult:
        """Check a draft without persistence or external side effects."""

    def commit(
        self,
        draft: ActivityDraft,
        *,
        preflight: ActivityPreflightResult,
    ) -> ActivityRecord:
        """Persist only a validated draft after the originating Turn settles."""

    def get(self, activity_id: ActivityId) -> Optional[ActivityRecord]:
        """Read one committed Activity."""

    def list(self) -> Tuple[ActivityRecord, ...]:
        """Read one atomic committed Activity snapshot for Brain/Lab projection."""

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
        """Commit one version-checked state transition and return its event."""

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
        """Settle the current external step from a real execution receipt."""


class InMemoryActivityStore(ActivityStorePort):
    """Small explicit store used when no persistence Adapter is injected."""

    def __init__(self) -> None:
        self._records: dict[ActivityId, ActivityRecord] = {}
        self._idempotency: dict[str, ActivityId] = {}
        self._lock = RLock()

    def preflight(
        self,
        draft: ActivityDraft,
        *,
        now: UTCDateTime,
    ) -> ActivityPreflightResult:
        with self._lock:
            return self._preflight(draft, now=now)

    def _preflight(
        self,
        draft: ActivityDraft,
        *,
        now: UTCDateTime,
    ) -> ActivityPreflightResult:
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
        existing_id = self._idempotency.get(draft.idempotency_key)
        if existing_id is not None and self._records[existing_id].draft != draft:
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
        existing_activity = self._records.get(draft.activity_id)
        if existing_activity is not None and existing_activity.draft != draft:
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
        with self._lock:
            return self._commit(draft, preflight=preflight)

    def _commit(
        self,
        draft: ActivityDraft,
        *,
        preflight: ActivityPreflightResult,
    ) -> ActivityRecord:
        if preflight.activity_id != draft.activity_id:
            raise ActivityTransitionError("Activity Preflight belongs to another draft")
        if preflight.status is not ActivityPreflightStatus.VALIDATED:
            raise ActivityTransitionError("only a validated Activity draft may commit")
        existing_activity = self._records.get(draft.activity_id)
        if existing_activity is not None and existing_activity.draft != draft:
            raise ActivityTransitionError(
                "Activity ID already belongs to another draft"
            )
        existing_id = self._idempotency.get(draft.idempotency_key)
        if existing_id is not None:
            existing = self._records[existing_id]
            if existing.draft != draft:
                raise ActivityTransitionError("Activity idempotency key conflict")
            return existing
        state = (
            ActivityState.WAITING
            if draft.wake_at is not None
            else ActivityState.RUNNING
        )
        record = ActivityRecord(
            activity_id=draft.activity_id,
            revision=0,
            state=state,
            draft=draft,
            created_at=draft.created_at,
            updated_at=draft.created_at,
            next_wakeup_at=draft.wake_at,
            current_step_id=None
            if state is ActivityState.WAITING
            else draft.steps[0].step_id,
            progress=tuple(
                ActivityStepProgress(step_id=step.step_id) for step in draft.steps
            ),
        )
        self._records[draft.activity_id] = record
        self._idempotency[draft.idempotency_key] = draft.activity_id
        return record

    def get(self, activity_id: ActivityId) -> Optional[ActivityRecord]:
        with self._lock:
            return self._records.get(activity_id)

    def list(self) -> Tuple[ActivityRecord, ...]:
        with self._lock:
            return tuple(self._records.values())

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
        with self._lock:
            return self._transition(
                activity_id,
                expected_revision=expected_revision,
                target=target,
                now=now,
                reason=reason,
                next_wakeup_at=next_wakeup_at,
            )

    def _transition(
        self,
        activity_id: ActivityId,
        *,
        expected_revision: int,
        target: ActivityState,
        now: UTCDateTime,
        reason: Optional[str] = None,
        next_wakeup_at: Optional[UTCDateTime] = None,
    ) -> ActivityStateEvent:
        current = self._records.get(activity_id)
        if current is None:
            raise ActivityTransitionError(f"Activity not found: {activity_id}")
        if current.revision != expected_revision:
            raise ActivityTransitionError("Activity revision conflict")
        updated, event = transition_activity(
            current,
            target,
            now=now,
            reason=reason,
            next_wakeup_at=next_wakeup_at,
        )
        self._records[activity_id] = updated
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
        with self._lock:
            return self._settle_step(
                activity_id,
                expected_revision=expected_revision,
                receipt_id=receipt_id,
                now=now,
                success=success,
                reason=reason,
            )

    def _settle_step(
        self,
        activity_id: ActivityId,
        *,
        expected_revision: int,
        receipt_id: EventId,
        now: UTCDateTime,
        success: bool,
        reason: Optional[str] = None,
    ) -> ActivityStateEvent:
        current = self._records.get(activity_id)
        if current is None:
            raise ActivityTransitionError(f"Activity not found: {activity_id}")
        if current.revision != expected_revision:
            raise ActivityTransitionError("Activity revision conflict")
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
        self._records[activity_id] = updated.model_copy(update={"progress": progress})
        return event


__all__ = (
    "ActivityDraft",
    "ActivityId",
    "ActivityPreflightResult",
    "ActivityPreflightStatus",
    "ActivityRecord",
    "ActivityState",
    "ActivityStateEvent",
    "ActivityStep",
    "ActivityStepKind",
    "ActivityStepProgress",
    "ActivityStorePort",
    "ActivityTransitionError",
    "InMemoryActivityStore",
    "activity_scope_for_record",
    "activity_state_event_to_perception",
    "transition_activity",
)
