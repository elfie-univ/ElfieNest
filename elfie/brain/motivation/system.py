"""Bounded fixed-drive motivation for the first autonomous-life slice."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional, Tuple

from pydantic import Field, StringConstraints
from typing_extensions import Annotated

from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.workspace.contracts import (
    ActivityPayload,
    ActivitySignal,
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
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
MotivationStatus = Literal["ready", "blocked", "cooldown", "satisfied"]


class RecoveryDriveCandidate(FrozenContractModel):
    """A bounded candidate that must re-enter Brain as an Activity Turn."""

    candidate_id: EventId
    drive_id: Literal["recovery"] = "recovery"
    goal: _NonBlankText
    reason: _NonBlankText
    pressure: _Ratio
    created_at: UTCDateTime
    cause_event_ids: Tuple[EventId, ...] = Field(min_length=1)


@dataclass(frozen=True)
class MotivationCheckpoint:
    """Persistence-neutral state needed to suppress repeated drive firing."""

    revision: int
    last_updated_at: datetime
    pressure: float
    status: MotivationStatus
    last_trigger_id: Optional[EventId]
    cooldown_until: Optional[datetime]
    satisfaction_until: Optional[datetime]


class MotivationRestoreError(ValueError):
    """Raised when a motivation checkpoint would rewind drive state."""


class MotivationSystem:
    """Own one fixed, low-risk recovery drive with explicit suppression."""

    def __init__(
        self,
        *,
        initial_at: datetime,
        energy_threshold: float = 20.0,
        fatigue_threshold: float = 75.0,
        cooldown_seconds: float = 300.0,
        satisfaction_seconds: float = 600.0,
    ) -> None:
        self._energy_threshold = energy_threshold
        self._fatigue_threshold = fatigue_threshold
        self._cooldown_seconds = cooldown_seconds
        self._satisfaction_seconds = satisfaction_seconds
        self._revision = 0
        self._last_updated_at = initial_at
        self._pressure = 0.0
        self._status: Literal["ready", "blocked", "cooldown", "satisfied"] = "ready"
        self._last_trigger_id: Optional[EventId] = None
        self._cooldown_until: Optional[datetime] = None
        self._satisfaction_until: Optional[datetime] = None

    def evaluate(
        self,
        *,
        energy: float,
        fatigue: float,
        sleeping: bool,
        now: UTCDateTime,
        blocked: bool,
    ) -> Optional[RecoveryDriveCandidate]:
        """Evaluate the recovery drive without creating Activity or actions."""
        if now < self._last_updated_at:
            raise MotivationRestoreError("motivation time cannot move backwards")
        pressure = self._calculate_pressure(energy=energy, fatigue=fatigue)
        self._last_updated_at = now
        self._pressure = pressure
        if sleeping or pressure <= 0.0:
            self._status = (
                "satisfied"
                if self._satisfaction_until is not None
                and now < self._satisfaction_until
                else "ready"
            )
            self._commit_revision()
            return None
        if blocked:
            self._status = "blocked"
            self._commit_revision()
            return None
        if self._satisfaction_until is not None and now < self._satisfaction_until:
            self._status = "satisfied"
            self._commit_revision()
            return None
        if self._cooldown_until is not None and now < self._cooldown_until:
            self._status = "cooldown"
            self._commit_revision()
            return None

        self._revision += 1
        candidate_id = EventId(f"motivation:recovery:{self._revision}")
        self._last_trigger_id = candidate_id
        self._cooldown_until = now + timedelta(seconds=self._cooldown_seconds)
        self._status = "cooldown"
        return RecoveryDriveCandidate(
            candidate_id=candidate_id,
            goal="恢复能量和疲劳，优先选择安全的休息方式",
            reason=(
                f"恢复驱力压力达到 {pressure:.2f}；能量 {energy:.1f}，疲劳 {fatigue:.1f}"
            ),
            pressure=pressure,
            created_at=now,
            cause_event_ids=(EventId(f"motivation-clock:{now.timestamp():.6f}"),),
        )

    def mark_handled(
        self,
        candidate_id: EventId,
        *,
        now: UTCDateTime,
        success: bool,
    ) -> bool:
        """Record one bounded Activity Turn outcome for the last candidate."""
        if candidate_id != self._last_trigger_id:
            return False
        if now < self._last_updated_at:
            raise MotivationRestoreError("motivation time cannot move backwards")
        self._last_updated_at = now
        self._revision += 1
        if success:
            self._satisfaction_until = now + timedelta(
                seconds=self._satisfaction_seconds
            )
            self._status = "satisfied"
        else:
            self._status = "cooldown"
        return True

    def snapshot(self, captured_at: UTCDateTime) -> MotivationSnapshot:
        """Return the current drive state for one immutable Brain context."""
        if captured_at < self._last_updated_at:
            raise MotivationRestoreError(
                "motivation snapshot time cannot move backwards"
            )
        return MotivationSnapshot(
            revision=self._revision,
            captured_at=captured_at,
            recovery_pressure=self._pressure,
            recovery_status=self._status,
            last_trigger_id=self._last_trigger_id,
            cooldown_until=self._cooldown_until,
            satisfaction_until=self._satisfaction_until,
        )

    def checkpoint(self) -> MotivationCheckpoint:
        """Capture suppression state for the Brain continuity checkpoint."""
        return MotivationCheckpoint(
            revision=self._revision,
            last_updated_at=self._last_updated_at,
            pressure=self._pressure,
            status=self._status,
            last_trigger_id=self._last_trigger_id,
            cooldown_until=self._cooldown_until,
            satisfaction_until=self._satisfaction_until,
        )

    def validate_checkpoint(self, checkpoint: MotivationCheckpoint) -> None:
        """Reject checkpoints that rewind the drive or contain invalid values."""
        if checkpoint.revision < self._revision:
            raise MotivationRestoreError("motivation checkpoint revision is older")
        if (
            checkpoint.revision == self._revision
            and checkpoint.last_updated_at < self._last_updated_at
        ):
            raise MotivationRestoreError("motivation checkpoint time is older")
        if not 0.0 <= checkpoint.pressure <= 1.0:
            raise MotivationRestoreError("motivation checkpoint pressure is invalid")
        if checkpoint.status not in {"ready", "blocked", "cooldown", "satisfied"}:
            raise MotivationRestoreError("motivation checkpoint status is invalid")

    def restore(self, checkpoint: MotivationCheckpoint) -> None:
        """Restore a validated drive suppression checkpoint."""
        self.validate_checkpoint(checkpoint)
        self._revision = checkpoint.revision
        self._last_updated_at = checkpoint.last_updated_at
        self._pressure = checkpoint.pressure
        self._status = checkpoint.status
        self._last_trigger_id = checkpoint.last_trigger_id
        self._cooldown_until = checkpoint.cooldown_until
        self._satisfaction_until = checkpoint.satisfaction_until

    def _calculate_pressure(self, *, energy: float, fatigue: float) -> float:
        energy_pressure = max(
            0.0,
            min(1.0, (self._energy_threshold - energy) / self._energy_threshold),
        )
        fatigue_pressure = max(
            0.0,
            min(
                1.0,
                (fatigue - self._fatigue_threshold) / (100.0 - self._fatigue_threshold),
            ),
        )
        return max(energy_pressure, fatigue_pressure)

    def _commit_revision(self) -> None:
        self._revision += 1


def recovery_candidate_to_perception(
    candidate: RecoveryDriveCandidate,
    *,
    elfie_id: ElfieId,
) -> PerceptionEvent:
    """Turn a drive candidate into one stable Internal perception event."""
    occurred_at = candidate.created_at
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=candidate.candidate_id,
            elfie_id=elfie_id,
            source=ActorRef(
                actor_id=ActorId(f"{elfie_id}:motivation"),
                source_kind="motivation",
            ),
            occurred_at=occurred_at,
            received_at=occurred_at,
            trace_id=TraceId(f"motivation:{candidate.candidate_id}"),
            causation_id=candidate.cause_event_ids[0],
            correlation_id=CorrelationId(str(candidate.candidate_id)),
            priority=Priority.LOW,
        ),
        payload=ActivityPayload(
            type="activity",
            signal=ActivitySignal.MOTIVATION,
            detail=json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False),
        ),
        salience=0.35,
    )


__all__ = (
    "MotivationCheckpoint",
    "MotivationRestoreError",
    "MotivationSystem",
    "RecoveryDriveCandidate",
    "recovery_candidate_to_perception",
)
