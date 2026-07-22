"""Observable coalescing and bounded-sample loss accounting."""

from dataclasses import dataclass
from typing import Dict, Tuple

from elfie.brain.perception_types import CoalescedSummary, DroppedSummary
from elfie.message_types import EventId


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class _Counter:
    seq: int
    count: int
    event_ids: Tuple[EventId, ...]


class WorkspaceLossLedger:
    """Accumulate loss facts until their corresponding frame commits."""

    def __init__(self) -> None:
        self._coalesced: Dict[str, _Counter] = {}
        self._dropped: Dict[str, _Counter] = {}

    def record_coalesced(self, key: str, seq: int, event_id: EventId) -> None:
        self._increment(self._coalesced, key, seq, event_id)

    def record_dropped(self, reason: str, seq: int, event_id: EventId) -> None:
        self._increment(self._dropped, reason, seq, event_id)

    def coalesced_summaries(self, cutoff: int) -> Tuple[CoalescedSummary, ...]:
        return tuple(
            CoalescedSummary(
                key=key,
                count=counter.count,
                latest_event_id=counter.event_ids[-1],
            )
            for key, counter in self._coalesced.items()
            if counter.seq <= cutoff
        )

    def dropped_summaries(self, cutoff: int) -> Tuple[DroppedSummary, ...]:
        return tuple(
            DroppedSummary(
                reason=reason,
                count=counter.count,
                event_ids=counter.event_ids,
            )
            for reason, counter in self._dropped.items()
            if counter.seq <= cutoff
        )

    def commit(self, cutoff: int) -> None:
        self._coalesced = {
            key: counter
            for key, counter in self._coalesced.items()
            if counter.seq > cutoff
        }
        self._dropped = {
            key: counter
            for key, counter in self._dropped.items()
            if counter.seq > cutoff
        }

    @staticmethod
    def _increment(
        counters: Dict[str, _Counter],
        key: str,
        seq: int,
        event_id: EventId,
    ) -> None:
        current = counters.get(key)
        if current is None:
            counters[key] = _Counter(seq, 1, (event_id,))
            return
        counters[key] = _Counter(
            seq, current.count + 1, current.event_ids + (event_id,)
        )


__all__ = ("WorkspaceLossLedger",)
