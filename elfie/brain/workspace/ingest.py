"""Bounded deduplication and receipt creation for perception ingestion."""

from __future__ import annotations

import json
from collections import OrderedDict
from hashlib import sha256
from typing import Optional, Tuple

from elfie.brain.workspace.contracts import (
    IngestDisposition,
    IngestReceipt,
    PerceptionWrite,
    WorkspaceSeenEvent,
)
from elfie.brain.workspace.types import FrameLifecycleError
from elfie.message_types import EventId


class WorkspaceIngestIndex:
    """Track recently admitted IDs without exposing workspace collections."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise FrameLifecycleError("dedupe capacity must be positive")
        self._capacity = capacity
        self._entries: OrderedDict[EventId, tuple[int, str]] = OrderedDict()

    def duplicate_seq(self, event_id: EventId) -> Optional[int]:
        entry = self._entries.get(event_id)
        return entry[0] if entry is not None else None

    def duplicate(self, write: PerceptionWrite) -> tuple[int, bool] | None:
        """Return the prior sequence and whether the complete write is equal."""

        entry = self._entries.get(write.meta.event_id)
        if entry is None:
            return None
        seq, digest = entry
        return seq, digest == self.digest(write)

    def remember(self, write: PerceptionWrite, seq: int) -> None:
        event_id = write.meta.event_id
        self._entries[event_id] = (seq, self.digest(write))
        self._entries.move_to_end(event_id)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def restore(self, entry: WorkspaceSeenEvent) -> None:
        self._entries[entry.event_id] = (entry.ingest_seq, entry.write_digest)
        self._entries.move_to_end(entry.event_id)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    @staticmethod
    def digest(write: PerceptionWrite) -> str:
        normalized = json.dumps(
            write.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(normalized.encode("utf-8")).hexdigest()

    def entries(self) -> Tuple[WorkspaceSeenEvent, ...]:
        """Return the bounded dedupe window in admission order."""
        return tuple(
            WorkspaceSeenEvent(
                event_id=event_id,
                ingest_seq=seq,
                write_digest=digest,
            )
            for event_id, (seq, digest) in self._entries.items()
        )

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
