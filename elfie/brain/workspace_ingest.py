"""Bounded deduplication and receipt creation for perception ingestion."""

from collections import OrderedDict
from typing import Optional

from elfie.brain.perception_types import IngestDisposition, IngestReceipt
from elfie.brain.workspace_types import FrameLifecycleError
from elfie.message_types import EventId


class WorkspaceIngestIndex:
    """Track recently admitted IDs without exposing workspace collections."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise FrameLifecycleError("dedupe capacity must be positive")
        self._capacity = capacity
        self._sequences: OrderedDict[EventId, int] = OrderedDict()

    def duplicate_seq(self, event_id: EventId) -> Optional[int]:
        return self._sequences.get(event_id)

    def remember(self, event_id: EventId, seq: int) -> None:
        self._sequences[event_id] = seq
        self._sequences.move_to_end(event_id)
        while len(self._sequences) > self._capacity:
            self._sequences.popitem(last=False)

    @staticmethod
    def receipt(
        event_id: EventId,
        disposition: IngestDisposition,
        ingest_seq: Optional[int],
        retryable: bool,
        reason: Optional[str],
    ) -> IngestReceipt:
        return IngestReceipt(
            event_id=event_id,
            disposition=disposition,
            ingest_seq=ingest_seq,
            retryable=retryable,
            reason=reason,
        )


__all__ = ("WorkspaceIngestIndex",)
