"""Pure hybrid policy deciding when accumulated perception becomes a turn."""

from datetime import timedelta
from typing import Optional

from elfie.brain.workspace.contracts import TriggerReason
from elfie.brain.workspace.types import TriggerMetrics
from elfie.message_types import FrozenContractModel, UTCDateTime


class TurnTriggerDecision(FrozenContractModel):
    """Cheap trigger outcome evaluated without scanning workspace contents."""

    reason: Optional[TriggerReason]
    cutoff_seq: Optional[int]


class TurnTriggerPolicy:
    """Combine urgent, conversation, salience, capacity, age, and autonomy."""

    def __init__(
        self,
        *,
        conversation_quiet_seconds: float = 0.4,
        conversation_hard_max_seconds: float = 2.0,
        oldest_event_seconds: float = 5.0,
        salience_threshold: float = 0.9,
        reliable_capacity_threshold: int = 128,
    ) -> None:
        self._quiet = timedelta(seconds=conversation_quiet_seconds)
        self._hard_max = timedelta(seconds=conversation_hard_max_seconds)
        self._oldest = timedelta(seconds=oldest_event_seconds)
        self._salience = salience_threshold
        self._capacity = reliable_capacity_threshold

    def evaluate(
        self,
        metrics: TriggerMetrics,
        *,
        now: UTCDateTime,
        autonomous_due: bool = False,
    ) -> TurnTriggerDecision:
        """Return the highest-priority reason for the current cutoff."""
        if metrics.stopped or metrics.latest_ingest_seq == 0:
            return TurnTriggerDecision(reason=None, cutoff_seq=None)
        reason = self._reason(metrics, now=now, autonomous_due=autonomous_due)
        return TurnTriggerDecision(
            reason=reason,
            cutoff_seq=metrics.latest_ingest_seq if reason is not None else None,
        )

    def _reason(
        self,
        metrics: TriggerMetrics,
        *,
        now: UTCDateTime,
        autonomous_due: bool,
    ) -> Optional[TriggerReason]:
        if metrics.critical_event_count > 0:
            return TriggerReason.EMERGENCY
        if autonomous_due:
            return TriggerReason.AUTONOMOUS
        if (
            metrics.oldest_social_at is not None
            and now - metrics.oldest_social_at >= self._hard_max
        ):
            return TriggerReason.CONVERSATION_HARD_MAX
        if (
            metrics.newest_social_at is not None
            and now - metrics.newest_social_at >= self._quiet
        ):
            return TriggerReason.CONVERSATION_QUIET
        if metrics.reliable_event_count >= self._capacity:
            return TriggerReason.CAPACITY
        if metrics.max_salience >= self._salience:
            return TriggerReason.SALIENCE
        if (
            metrics.oldest_event_at is not None
            and now - metrics.oldest_event_at >= self._oldest
        ):
            return TriggerReason.OLDEST_EVENT
        return None


__all__ = ("TurnTriggerDecision", "TurnTriggerPolicy")
