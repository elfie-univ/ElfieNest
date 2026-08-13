"""Bounded cognitive consolidation for one quiet, sleeping Brain window.

Cognitive Consolidation is deliberately a scheduler-facing Brain subsystem, not a
second memory implementation.  It may propose one bounded consolidation
candidate; only the resulting internal Turn receipt may commit the memory
change.  The subsystem never sends a message, touches a Body, or creates an
Activity itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Callable, Literal, Mapping, Optional, Tuple

from pydantic import Field, StringConstraints
from typing_extensions import Annotated

from elfie.brain.consolidation.contracts import CognitiveConsolidationSnapshot
from elfie.brain.workspace.contracts import (
    InternalPayload,
    InternalSignal,
    PerceptionEvent,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    CorrelationId,
    ElfieId,
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
CognitiveConsolidationStatus = Literal[
    "ready", "blocked", "cooldown", "satisfied", "unknown"
]


class CognitiveConsolidationCandidate(FrozenContractModel):
    """One bounded memory-consolidation request admitted as an Internal Turn."""

    candidate_id: EventId
    mode: Literal["consolidation"] = "consolidation"
    goal: _NonBlankText
    episode_ids: Tuple[_NonBlankText, ...] = Field(min_length=1)
    created_at: UTCDateTime
    cause_event_ids: Tuple[EventId, ...] = Field(min_length=1)


@dataclass(frozen=True)
class CognitiveConsolidationCheckpoint:
    """Persistence-neutral suppression and result state for continuity restore."""

    revision: int
    last_updated_at: datetime
    status: CognitiveConsolidationStatus
    last_trigger_id: Optional[EventId]
    cooldown_until: Optional[datetime]
    satisfaction_until: Optional[datetime]
    last_run_at: Optional[datetime]
    last_consolidated_count: int
    last_knowledge_created: int
    last_patterns_created: int
    pending_candidate: Optional[CognitiveConsolidationCandidate]


class CognitiveConsolidationRestoreError(ValueError):
    """Raised when an cognitive-consolidation checkpoint would rewind state."""


@dataclass(frozen=True)
class CognitiveConsolidationResult:
    """Small receipt-independent result exposed to Brain tests and observers."""

    consolidated_count: int
    knowledge_created: int
    patterns_created: int


class CognitiveConsolidationSystem:
    """Own quiet-window admission, suppression, and bounded consolidation."""

    def __init__(
        self,
        *,
        pending_episode_ids: Callable[[int], Tuple[str, ...]],
        consolidate: Callable[[int], Mapping[str, object]],
        initial_at: datetime,
        max_episodes: int = 8,
        cooldown_seconds: float = 300.0,
        satisfaction_seconds: float = 900.0,
    ) -> None:
        if max_episodes < 1:
            raise ValueError("max_episodes must be positive")
        self._pending_episode_ids = pending_episode_ids
        self._consolidate = consolidate
        self._max_episodes = max_episodes
        self._cooldown_seconds = cooldown_seconds
        self._satisfaction_seconds = satisfaction_seconds
        self._revision = 0
        self._last_updated_at = initial_at
        self._status: CognitiveConsolidationStatus = "ready"
        self._last_trigger_id: Optional[EventId] = None
        self._cooldown_until: Optional[datetime] = None
        self._satisfaction_until: Optional[datetime] = None
        self._last_run_at: Optional[datetime] = None
        self._last_consolidated_count = 0
        self._last_knowledge_created = 0
        self._last_patterns_created = 0
        self._pending_candidate: Optional[CognitiveConsolidationCandidate] = None
        self._lock = RLock()

    def evaluate(
        self,
        *,
        sleeping: bool,
        now: UTCDateTime,
        blocked: bool,
    ) -> Optional[CognitiveConsolidationCandidate]:
        """Read the quiet-window gate and optionally emit one idempotent candidate."""
        with self._lock:
            self._ensure_time(now)
            self._last_updated_at = now
            try:
                pending = tuple(self._pending_episode_ids(self._max_episodes))
            except Exception:
                self._status = "blocked"
                self._revision += 1
                return None
            if self._pending_candidate is not None:
                if not sleeping:
                    self._status = "ready"
                    self._revision += 1
                    return None
                if blocked:
                    self._status = "blocked"
                    self._revision += 1
                    return None
                self._status = "cooldown"
                self._revision += 1
                return self._pending_candidate
            if not pending:
                self._status = (
                    "satisfied"
                    if self._satisfaction_until is not None
                    and now < self._satisfaction_until
                    else "ready"
                )
                self._revision += 1
                return None
            if not sleeping:
                self._status = "ready"
                self._revision += 1
                return None
            if blocked:
                self._status = "blocked"
                self._revision += 1
                return None
            if self._satisfaction_until is not None and now < self._satisfaction_until:
                self._status = "satisfied"
                self._revision += 1
                return None
            if self._cooldown_until is not None and now < self._cooldown_until:
                self._status = "cooldown"
                self._revision += 1
                return None

            self._revision += 1
            candidate_id = EventId(f"consolidation:{self._revision}")
            self._last_trigger_id = candidate_id
            self._cooldown_until = now + timedelta(seconds=self._cooldown_seconds)
            self._status = "cooldown"
            self._pending_candidate = CognitiveConsolidationCandidate(
                candidate_id=candidate_id,
                goal="整理近期经历，提炼稳定记忆；本轮只允许更新记忆，不产生外部动作",
                episode_ids=pending,
                created_at=now,
                cause_event_ids=(
                    EventId(f"cognitive-consolidation-clock:{now.timestamp():.6f}"),
                ),
            )
            return self._pending_candidate

    def settle(
        self,
        candidate_id: EventId,
        *,
        now: UTCDateTime,
        success: bool,
    ) -> bool:
        """Commit only after the Internal Turn receipt; never call on evaluation."""
        with self._lock:
            self._ensure_time(now)
            candidate = self._pending_candidate
            if candidate is None or candidate.candidate_id != candidate_id:
                return False
            self._last_updated_at = now
            if not success:
                self._status = "cooldown"
                self._pending_candidate = None
                self._revision += 1
                return False
            try:
                current_ids = set(self._pending_episode_ids(self._max_episodes))
            except Exception:
                self._status = "cooldown"
                self._pending_candidate = None
                self._revision += 1
                return False
            if not set(candidate.episode_ids).issubset(current_ids):
                self._status = "cooldown"
                self._pending_candidate = None
                self._revision += 1
                return False
            try:
                result = self._consolidate(len(candidate.episode_ids))
            except Exception:
                self._status = "cooldown"
                self._pending_candidate = None
                self._revision += 1
                return False
            self._last_run_at = now
            self._last_consolidated_count = _result_int(result, "consolidated_count")
            self._last_knowledge_created = _result_int(result, "knowledge_created")
            self._last_patterns_created = _result_int(result, "patterns_created")
            self._satisfaction_until = now + timedelta(
                seconds=self._satisfaction_seconds
            )
            self._status = "satisfied"
            self._pending_candidate = None
            self._revision += 1
            return True

    def snapshot(self, captured_at: UTCDateTime) -> CognitiveConsolidationSnapshot:
        with self._lock:
            self._ensure_time(captured_at)
            try:
                pending_count = len(
                    tuple(self._pending_episode_ids(self._max_episodes))
                )
            except Exception:
                pending_count = (
                    len(self._pending_candidate.episode_ids)
                    if self._pending_candidate is not None
                    else 0
                )
            if self._pending_candidate is not None:
                pending_count = max(
                    pending_count, len(self._pending_candidate.episode_ids)
                )
            return CognitiveConsolidationSnapshot(
                revision=self._revision,
                captured_at=captured_at,
                status=self._status,
                pending_episode_count=pending_count,
                last_trigger_id=self._last_trigger_id,
                cooldown_until=self._cooldown_until,
                satisfaction_until=self._satisfaction_until,
                last_run_at=self._last_run_at,
                last_consolidated_count=self._last_consolidated_count,
                last_knowledge_created=self._last_knowledge_created,
                last_patterns_created=self._last_patterns_created,
            )

    def checkpoint(self) -> CognitiveConsolidationCheckpoint:
        with self._lock:
            return CognitiveConsolidationCheckpoint(
                revision=self._revision,
                last_updated_at=self._last_updated_at,
                status=self._status,
                last_trigger_id=self._last_trigger_id,
                cooldown_until=self._cooldown_until,
                satisfaction_until=self._satisfaction_until,
                last_run_at=self._last_run_at,
                last_consolidated_count=self._last_consolidated_count,
                last_knowledge_created=self._last_knowledge_created,
                last_patterns_created=self._last_patterns_created,
                pending_candidate=self._pending_candidate,
            )

    def validate_checkpoint(self, checkpoint: CognitiveConsolidationCheckpoint) -> None:
        with self._lock:
            if checkpoint.revision < self._revision:
                raise CognitiveConsolidationRestoreError(
                    "offline checkpoint revision is older"
                )
            if (
                checkpoint.revision == self._revision
                and checkpoint.last_updated_at < self._last_updated_at
            ):
                raise CognitiveConsolidationRestoreError(
                    "offline checkpoint time is older"
                )
            if checkpoint.status not in {
                "ready",
                "blocked",
                "cooldown",
                "satisfied",
                "unknown",
            }:
                raise CognitiveConsolidationRestoreError(
                    "offline checkpoint status is invalid"
                )
            if (
                min(
                    checkpoint.last_consolidated_count,
                    checkpoint.last_knowledge_created,
                    checkpoint.last_patterns_created,
                )
                < 0
            ):
                raise CognitiveConsolidationRestoreError(
                    "offline result counts are invalid"
                )

    def restore(self, checkpoint: CognitiveConsolidationCheckpoint) -> None:
        with self._lock:
            self.validate_checkpoint(checkpoint)
            self._revision = checkpoint.revision
            self._last_updated_at = checkpoint.last_updated_at
            self._status = checkpoint.status
            self._last_trigger_id = checkpoint.last_trigger_id
            self._cooldown_until = checkpoint.cooldown_until
            self._satisfaction_until = checkpoint.satisfaction_until
            self._last_run_at = checkpoint.last_run_at
            self._last_consolidated_count = checkpoint.last_consolidated_count
            self._last_knowledge_created = checkpoint.last_knowledge_created
            self._last_patterns_created = checkpoint.last_patterns_created
            self._pending_candidate = checkpoint.pending_candidate

    def _ensure_time(self, now: datetime) -> None:
        if now < self._last_updated_at:
            raise CognitiveConsolidationRestoreError(
                "cognitive consolidation time cannot move backwards"
            )


def consolidation_candidate_to_perception(
    candidate: CognitiveConsolidationCandidate,
    *,
    elfie_id: ElfieId,
) -> PerceptionEvent:
    """Represent a candidate as inert internal input with no response scope."""
    occurred_at = candidate.created_at
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=candidate.candidate_id,
            elfie_id=elfie_id,
            source=ActorRef(
                actor_id=ActorId(f"{elfie_id}:cognitive-consolidation"),
                source_kind="consolidation",
            ),
            occurred_at=occurred_at,
            received_at=occurred_at,
            trace_id=TraceId(f"cognitive-consolidation:{candidate.candidate_id}"),
            causation_id=candidate.cause_event_ids[0],
            correlation_id=CorrelationId(str(candidate.candidate_id)),
            priority=Priority.LOW,
        ),
        payload=InternalPayload(
            type="internal",
            signal=InternalSignal.COGNITIVE_CONSOLIDATION,
            detail=json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False),
        ),
        salience=0.25,
    )


def _result_int(result: Mapping[str, object], key: str) -> int:
    value = result.get(key, 0)
    return value if isinstance(value, int) and value >= 0 else 0


__all__ = (
    "CognitiveConsolidationCandidate",
    "CognitiveConsolidationCheckpoint",
    "CognitiveConsolidationRestoreError",
    "CognitiveConsolidationResult",
    "CognitiveConsolidationStatus",
    "CognitiveConsolidationSystem",
    "consolidation_candidate_to_perception",
)
