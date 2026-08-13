"""Small, deterministic candidate/validate/commit state lifecycle primitives."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Callable, Deque, Generic, Optional, Set, Tuple, TypeVar

from elfie.message_types import EventId, UTCDateTime

StateValue = TypeVar("StateValue")
StateValidator = Callable[[StateValue, StateValue], Optional[str]]


class StateCommitStatus(str, Enum):
    """Observable outcome of validating or committing one state candidate."""

    ACCEPTED = "accepted"
    COMMITTED = "committed"
    DUPLICATE = "duplicate"
    STALE = "stale"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StateCandidate(Generic[StateValue]):
    """An immutable proposal against one exact owner revision."""

    candidate_id: EventId
    owner: str
    base_revision: int
    source_event_ids: Tuple[EventId, ...]
    causation_id: Optional[EventId]
    created_at: UTCDateTime
    value: StateValue


@dataclass(frozen=True)
class VersionedState(Generic[StateValue]):
    """The latest committed value and its provenance."""

    revision: int
    committed_at: UTCDateTime
    source_event_ids: Tuple[EventId, ...]
    causation_id: Optional[EventId]
    value: StateValue


@dataclass(frozen=True)
class StateCheckpoint(Generic[StateValue]):
    """Serializable-in-spirit checkpoint data for a future persistence adapter."""

    revision: int
    committed_at: UTCDateTime
    source_event_ids: Tuple[EventId, ...]
    causation_id: Optional[EventId]
    value: StateValue
    committed_candidate_ids: Tuple[EventId, ...]


@dataclass(frozen=True)
class StateCommitReceipt:
    """Result of validation or commit, suitable for audit and tests."""

    candidate_id: EventId
    status: StateCommitStatus
    revision: int
    reason: Optional[str] = None


class StateRestoreError(RuntimeError):
    """Raised when a checkpoint would move an owner backwards in time."""


class VersionedStateStore(Generic[StateValue]):
    """Thread-safe in-memory owner with explicit stale and idempotency guards.

    This is deliberately a semantic Brain primitive, not a database adapter. A
    later persistence implementation can serialize ``StateCheckpoint`` without
    changing candidate validation or commit semantics.
    """

    def __init__(
        self,
        initial: VersionedState[StateValue],
        *,
        dedupe_capacity: int = 2048,
    ) -> None:
        if initial.revision < 0:
            raise ValueError("state revision cannot be negative")
        if dedupe_capacity < 1:
            raise ValueError("state dedupe capacity must be positive")
        self._current = initial
        self._dedupe_capacity = dedupe_capacity
        self._committed_ids: Set[EventId] = set()
        self._committed_order: Deque[EventId] = deque()
        self._lock = Lock()

    def snapshot(self) -> VersionedState[StateValue]:
        with self._lock:
            return self._current

    def checkpoint(self) -> StateCheckpoint[StateValue]:
        with self._lock:
            return StateCheckpoint(
                revision=self._current.revision,
                committed_at=self._current.committed_at,
                source_event_ids=self._current.source_event_ids,
                causation_id=self._current.causation_id,
                value=self._current.value,
                committed_candidate_ids=tuple(self._committed_order),
            )

    def validate(
        self,
        candidate: StateCandidate[StateValue],
        *,
        validator: StateValidator[StateValue] | None = None,
    ) -> StateCommitReceipt:
        """Validate without mutating the owner."""
        with self._lock:
            return self._validate_locked(candidate, validator)

    def commit(
        self,
        candidate: StateCandidate[StateValue],
        *,
        validator: StateValidator[StateValue] | None = None,
    ) -> StateCommitReceipt:
        """Validate and commit exactly one candidate under the owner lock."""
        with self._lock:
            validation = self._validate_locked(candidate, validator)
            if validation.status is not StateCommitStatus.ACCEPTED:
                return validation
            self._current = VersionedState(
                revision=self._current.revision + 1,
                committed_at=candidate.created_at,
                source_event_ids=candidate.source_event_ids,
                causation_id=candidate.causation_id,
                value=candidate.value,
            )
            self._remember(candidate.candidate_id)
            return StateCommitReceipt(
                candidate_id=candidate.candidate_id,
                status=StateCommitStatus.COMMITTED,
                revision=self._current.revision,
            )

    def restore(self, checkpoint: StateCheckpoint[StateValue]) -> None:
        """Restore a checkpoint without allowing a backwards revision."""
        with self._lock:
            if checkpoint.revision < self._current.revision:
                raise StateRestoreError(
                    "state checkpoint revision is older than current state"
                )
            self._current = VersionedState(
                revision=checkpoint.revision,
                committed_at=checkpoint.committed_at,
                source_event_ids=checkpoint.source_event_ids,
                causation_id=checkpoint.causation_id,
                value=checkpoint.value,
            )
            self._committed_ids = set(checkpoint.committed_candidate_ids)
            self._committed_order = deque(checkpoint.committed_candidate_ids)
            while len(self._committed_order) > self._dedupe_capacity:
                self._committed_ids.discard(self._committed_order.popleft())

    def _validate_locked(
        self,
        candidate: StateCandidate[StateValue],
        validator: StateValidator[StateValue] | None,
    ) -> StateCommitReceipt:
        if candidate.candidate_id in self._committed_ids:
            return StateCommitReceipt(
                candidate_id=candidate.candidate_id,
                status=StateCommitStatus.DUPLICATE,
                revision=self._current.revision,
                reason="candidate_already_committed",
            )
        if candidate.base_revision != self._current.revision:
            return StateCommitReceipt(
                candidate_id=candidate.candidate_id,
                status=StateCommitStatus.STALE,
                revision=self._current.revision,
                reason="base_revision_mismatch",
            )
        if validator is not None:
            reason = validator(self._current.value, candidate.value)
            if reason is not None:
                return StateCommitReceipt(
                    candidate_id=candidate.candidate_id,
                    status=StateCommitStatus.REJECTED,
                    revision=self._current.revision,
                    reason=reason,
                )
        return StateCommitReceipt(
            candidate_id=candidate.candidate_id,
            status=StateCommitStatus.ACCEPTED,
            revision=self._current.revision,
        )

    def _remember(self, candidate_id: EventId) -> None:
        self._committed_ids.add(candidate_id)
        self._committed_order.append(candidate_id)
        while len(self._committed_order) > self._dedupe_capacity:
            self._committed_ids.discard(self._committed_order.popleft())


__all__ = (
    "StateCandidate",
    "StateCheckpoint",
    "StateCommitReceipt",
    "StateCommitStatus",
    "StateRestoreError",
    "VersionedState",
    "VersionedStateStore",
)
