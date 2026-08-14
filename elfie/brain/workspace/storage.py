"""Private four-zone storage used by the perceptual workspace."""

from __future__ import annotations

from collections import OrderedDict, deque
from typing import Deque, Dict, NamedTuple, Optional, Tuple

from elfie.brain.workspace.contracts import (
    IngestDisposition,
    PerceptionEvent,
    PerceptionMediaSample,
    PerceptionStateUpdate,
    PerceptionWrite,
    TriggerReason,
    TurnFrame,
    WorkspaceLossRecord,
    WorkspacePendingWrite,
    domain_for_scope,
    interaction_scope_for,
    response_scope_for,
    scope_key,
)
from elfie.brain.workspace.event_metrics import WorkspaceEventMetrics
from elfie.brain.workspace.loss_ledger import WorkspaceLossLedger
from elfie.brain.workspace.types import (
    FrameLifecycleError,
    ProcessingFailureEvent,
    WorkspaceStorageMetrics,
    build_processing_failure,
)
from elfie.message_types import ElfieId, EventId, UTCDateTime


class _EventEntry(NamedTuple):
    seq: int
    item: PerceptionEvent


class _StateEntry(NamedTuple):
    seq: int
    item: PerceptionStateUpdate


class _MediaEntry(NamedTuple):
    seq: int
    item: PerceptionMediaSample


class WorkspaceStorage:
    """Mutable accumulator accessed only while the workspace lock is held."""

    def __init__(
        self,
        *,
        journal_capacity: int,
        state_capacity: int,
        media_per_stream_capacity: int,
    ) -> None:
        if min(journal_capacity, state_capacity, media_per_stream_capacity) < 1:
            raise FrameLifecycleError("workspace storage capacities must be positive")
        self._journal_capacity = journal_capacity
        self._state_capacity = state_capacity
        self._media_capacity = media_per_stream_capacity
        self._journal: Deque[_EventEntry] = deque()
        self._failure_queue: Deque[_EventEntry] = deque()
        self._state: OrderedDict[Tuple[str, str], _StateEntry] = OrderedDict()
        self._media: Dict[Tuple[str, str], Deque[_MediaEntry]] = {}
        self._loss = WorkspaceLossLedger()
        self._event_metrics = WorkspaceEventMetrics()
        self._dead_letters: Deque[ProcessingFailureEvent] = deque()
        self._media_count = 0

    @property
    def journal_full(self) -> bool:
        return len(self._journal) >= self._journal_capacity

    def store(self, item: PerceptionWrite, seq: int) -> IngestDisposition:
        if isinstance(item, PerceptionEvent):
            self._journal.append(_EventEntry(seq, item))
            self._event_metrics.record(item)
            return IngestDisposition.ACCEPTED
        if isinstance(item, PerceptionStateUpdate):
            return self._store_state(item, seq)
        return self._store_media(item, seq)

    def metrics(self) -> WorkspaceStorageMetrics:
        return self._event_metrics.snapshot(
            reliable_event_count=len(self._journal) + len(self._failure_queue),
            state_key_count=len(self._state),
            media_sample_count=self._media_count,
        )

    def build_frame(
        self,
        *,
        frame_id: EventId,
        elfie_id: ElfieId,
        revision: int,
        requested_cutoff: int,
        frame_event_capacity: int,
        reason: TriggerReason,
        captured_at: UTCDateTime,
    ) -> Optional[TurnFrame]:
        reliable = tuple(
            entry
            for entry in tuple(self._failure_queue) + tuple(self._journal)
            if entry.seq <= requested_cutoff
        )
        reliable = tuple(sorted(reliable, key=lambda entry: entry.seq))
        state_entries = tuple(
            entry for entry in self._state.values() if entry.seq <= requested_cutoff
        )
        media_entries = tuple(
            entry
            for stream in self._media.values()
            for entry in stream
            if entry.seq <= requested_cutoff
        )
        media_entries = tuple(sorted(media_entries, key=lambda entry: entry.seq))
        candidates = tuple(
            sorted(
                reliable + state_entries + media_entries,
                key=lambda entry: entry.seq,
            )
        )
        if not candidates:
            return None
        interaction_scope = interaction_scope_for(candidates[0].item)
        selected_scope = scope_key(candidates[0].item)
        compatible_reliable = tuple(
            entry for entry in reliable if scope_key(entry.item) == selected_scope
        )
        selected = compatible_reliable[:frame_event_capacity]
        cutoff = requested_cutoff
        if len(selected) < len(compatible_reliable):
            cutoff = selected[-1].seq
        states = tuple(
            entry.item
            for entry in state_entries
            if entry.seq <= cutoff and scope_key(entry.item) == selected_scope
        )
        selected_media = tuple(
            entry.item
            for entry in media_entries
            if entry.seq <= cutoff and scope_key(entry.item) == selected_scope
        )
        return TurnFrame(
            frame_id=frame_id,
            elfie_id=elfie_id,
            revision=revision,
            captured_at=captured_at,
            cutoff_seq=cutoff,
            trigger_reason=reason,
            source_domain=domain_for_scope(interaction_scope),
            interaction_scope=interaction_scope,
            response_scope=response_scope_for(interaction_scope),
            events=tuple(entry.item for entry in selected),
            state_updates=states,
            media_samples=selected_media,
            coalesced=self._loss.coalesced_summaries(cutoff),
            dropped=self._loss.dropped_summaries(cutoff),
        )

    def commit(self, frame: TurnFrame) -> None:
        event_ids = {event.meta.event_id for event in frame.events}
        state_ids = {state.meta.event_id for state in frame.state_updates}
        media_ids = {sample.meta.event_id for sample in frame.media_samples}
        self._journal = deque(
            entry
            for entry in self._journal
            if entry.item.meta.event_id not in event_ids
        )
        self._failure_queue = deque(
            entry
            for entry in self._failure_queue
            if entry.item.meta.event_id not in event_ids
        )
        self._state = OrderedDict(
            (key, entry)
            for key, entry in self._state.items()
            if entry.item.meta.event_id not in state_ids
        )
        for stream_id in tuple(self._media):
            retained = deque(
                entry
                for entry in self._media[stream_id]
                if entry.item.meta.event_id not in media_ids
            )
            if retained:
                self._media[stream_id] = retained
            else:
                del self._media[stream_id]
        self._loss.commit(frame.cutoff_seq)
        self._media_count = sum(len(stream) for stream in self._media.values())
        self._event_metrics.refresh(
            entry.item for entry in tuple(self._failure_queue) + tuple(self._journal)
        )

    def enqueue_processing_failure(
        self,
        *,
        seq: int,
        elfie_id: ElfieId,
        failed_frame: TurnFrame,
        reason: str,
        occurred_at: UTCDateTime,
    ) -> ProcessingFailureEvent:
        failure = build_processing_failure(
            elfie_id=elfie_id,
            failed_frame_id=failed_frame.frame_id,
            failed_cutoff_seq=failed_frame.cutoff_seq,
            reason=reason,
            occurred_at=occurred_at,
        )
        self._failure_queue.append(_EventEntry(seq, failure))
        self._dead_letters.append(failure)
        self._event_metrics.record(failure)
        return failure

    def dead_letters(self) -> Tuple[ProcessingFailureEvent, ...]:
        return tuple(self._dead_letters)

    def pending_writes(self) -> Tuple[PerceptionWrite, ...]:
        """Return the complete current semantic cut in ingest order."""
        entries: list[tuple[int, PerceptionWrite]] = [
            (entry.seq, entry.item)
            for entry in tuple(self._failure_queue) + tuple(self._journal)
        ]
        entries.extend((entry.seq, entry.item) for entry in self._state.values())
        entries.extend(
            (entry.seq, entry.item)
            for stream in self._media.values()
            for entry in stream
        )
        return tuple(item for _, item in sorted(entries, key=lambda item: item[0]))

    def pending_entries(self) -> Tuple[WorkspacePendingWrite, ...]:
        """Return pending writes with their stable original sequences."""
        entries: list[WorkspacePendingWrite] = [
            WorkspacePendingWrite(ingest_seq=entry.seq, write=entry.item)
            for entry in tuple(self._failure_queue) + tuple(self._journal)
        ]
        entries.extend(
            WorkspacePendingWrite(ingest_seq=entry.seq, write=entry.item)
            for entry in self._state.values()
        )
        entries.extend(
            WorkspacePendingWrite(ingest_seq=entry.seq, write=entry.item)
            for stream in self._media.values()
            for entry in stream
        )
        return tuple(sorted(entries, key=lambda item: item.ingest_seq))

    def loss_records(self) -> Tuple[WorkspaceLossRecord, ...]:
        """Return restart-safe observable-loss evidence."""
        return self._loss.records()

    def restore_loss_records(self, records: Tuple[WorkspaceLossRecord, ...]) -> None:
        """Restore loss evidence after pending writes have been rebuilt."""
        self._loss.restore(records)

    def _store_state(
        self,
        item: PerceptionStateUpdate,
        seq: int,
    ) -> IngestDisposition:
        disposition = IngestDisposition.ACCEPTED
        scoped_key = (item.body_id, item.state_key)
        previous = self._state.pop(scoped_key, None)
        if previous is not None:
            self._loss.record_coalesced(
                f"state:{item.state_key}",
                seq,
                previous.item.meta.event_id,
            )
            disposition = IngestDisposition.COALESCED
        elif len(self._state) >= self._state_capacity:
            _, dropped = self._state.popitem(last=False)
            self._loss.record_dropped(
                "state_capacity",
                seq,
                dropped.item.meta.event_id,
            )
            disposition = IngestDisposition.COALESCED
        self._state[scoped_key] = _StateEntry(seq, item)
        return disposition

    def _store_media(
        self,
        item: PerceptionMediaSample,
        seq: int,
    ) -> IngestDisposition:
        stream_key = (item.body_id, item.stream_id)
        stream = self._media.setdefault(stream_key, deque())
        disposition = IngestDisposition.ACCEPTED
        if len(stream) >= self._media_capacity:
            dropped = stream.popleft()
            self._media_count -= 1
            self._loss.record_dropped(
                "media_capacity",
                seq,
                dropped.item.meta.event_id,
            )
            disposition = IngestDisposition.COALESCED
        stream.append(_MediaEntry(seq, item))
        self._media_count += 1
        return disposition


__all__ = ("WorkspaceStorage",)
