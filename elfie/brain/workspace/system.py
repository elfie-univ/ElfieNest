"""Thread-safe MPSC workspace and reliable perception-frame lifecycle."""

from __future__ import annotations

from typing import Optional, Tuple
from uuid import uuid4

from elfie.brain.workspace.contracts import (
    IngestDisposition,
    IngestReceipt,
    PerceptionEvent,
    PerceptionWrite,
    ProcessingFailureEvent,
    TriggerReason,
    TurnFrame,
    WorkspacePersistentState,
)
from elfie.brain.workspace.ingest import WorkspaceIngestIndex
from elfie.brain.workspace.ports import WorkspacePersistencePort
from elfie.brain.workspace.signal import Clock, WorkspaceSignal, utc_now
from elfie.brain.workspace.storage import WorkspaceStorage
from elfie.brain.workspace.types import (
    ActiveClaimError,
    FrameLifecycleError,
    ReleaseDisposition,
    TriggerMetrics,
    WaitStatus,
    WorkspaceClaim,
)
from elfie.message_types import ElfieId, EventId, TurnId, UTCDateTime


class EventWorkspace:
    """Three-domain MPSC workspace with claim, replay, and durable commit."""

    def __init__(
        self,
        elfie_id: ElfieId,
        *,
        clock: Clock = utc_now,
        journal_capacity: int = 1024,
        frame_event_capacity: int = 128,
        state_capacity: int = 256,
        media_per_stream_capacity: int = 64,
        dedupe_capacity: int = 4096,
        persistence: WorkspacePersistencePort | None = None,
    ) -> None:
        if frame_event_capacity < 1:
            raise FrameLifecycleError("frame event capacity must be positive")
        self._elfie_id = elfie_id
        self._frame_capacity = frame_event_capacity
        self._journal_capacity = journal_capacity
        self._state_capacity = state_capacity
        self._media_capacity = media_per_stream_capacity
        self._dedupe_capacity = dedupe_capacity
        self._persistence = persistence
        self._signal = WorkspaceSignal(clock)
        self._storage = WorkspaceStorage(
            journal_capacity=journal_capacity,
            state_capacity=state_capacity,
            media_per_stream_capacity=media_per_stream_capacity,
        )
        self._ingest = WorkspaceIngestIndex(dedupe_capacity)
        self._sealed: Optional[TurnFrame] = None
        self._active: Optional[WorkspaceClaim] = None
        self._attempts: dict[EventId, int] = {}
        self._next_seq = 0
        self._frame_revision = 0
        if self._persistence is not None:
            self._restore_persistent_state(self._persistence.load_workspace_state())

    def publish(self, item: PerceptionWrite) -> IngestReceipt:
        """Atomically ingest one typed write without hiding loss."""
        with self._signal.locked():
            event_id = item.meta.event_id
            if self._signal.stopped or item.meta.elfie_id != self._elfie_id:
                reason = (
                    "workspace_stopped" if self._signal.stopped else "foreign_elfie"
                )
                return self._ingest.receipt(
                    event_id, IngestDisposition.REJECTED, None, False, reason
                )
            duplicate = self._ingest.duplicate(item)
            if duplicate is not None:
                duplicate_seq, same_write = duplicate
                return self._ingest.receipt(
                    event_id,
                    (
                        IngestDisposition.DUPLICATE
                        if same_write
                        else IngestDisposition.REJECTED
                    ),
                    duplicate_seq if same_write else None,
                    False,
                    "duplicate" if same_write else "event_id_conflict",
                )
            if isinstance(item, PerceptionEvent) and self._storage.journal_full:
                return self._ingest.receipt(
                    event_id,
                    IngestDisposition.BACKPRESSURED,
                    None,
                    True,
                    "journal_capacity",
                )
            previous = self._persistent_state()
            seq = self._allocate_seq()
            disposition = self._storage.store(item, seq)
            self._ingest.remember(item, seq)
            try:
                self._persist_pending()
            except Exception:
                self._restore_persistent_state(previous)
                raise
            self._signal.bump()
            return self._ingest.receipt(event_id, disposition, seq, False, None)

    def metrics(self) -> TriggerMetrics:
        """Return trigger inputs without scanning workspace collections."""
        with self._signal.locked():
            storage = self._storage.metrics()
            return TriggerMetrics(
                revision=self._signal.revision,
                latest_ingest_seq=self._next_seq,
                reliable_event_count=storage.reliable_event_count,
                state_key_count=storage.state_key_count,
                media_sample_count=storage.media_sample_count,
                oldest_event_at=storage.oldest_event_at,
                newest_event_at=storage.newest_event_at,
                oldest_social_at=storage.oldest_social_at,
                newest_social_at=storage.newest_social_at,
                critical_event_count=storage.critical_event_count,
                max_salience=storage.max_salience,
                stopped=self._signal.stopped,
            )

    def seal(
        self, *, reason: TriggerReason, captured_at: UTCDateTime
    ) -> Optional[EventId]:
        """Seal all currently ingested writes unless a replay already exists."""
        with self._signal.locked():
            self._ensure_no_active()
            if self._sealed is None:
                self._sealed = self._build_frame(self._next_seq, reason, captured_at)
            return None if self._sealed is None else self._sealed.frame_id

    def claim(self, frame_id: EventId, turn_id: TurnId) -> TurnFrame:
        """Claim a sealed frame for one turn."""
        with self._signal.locked():
            self._ensure_no_active()
            if self._sealed is None or self._sealed.frame_id != frame_id:
                raise FrameLifecycleError("sealed frame ID does not match")
            frame = self._sealed
            self._sealed = None
            self._active = WorkspaceClaim(frame, turn_id)
            return frame

    def claim_frame(
        self,
        cutoff_seq: int,
        *,
        turn_id: TurnId,
        reason: TriggerReason,
        captured_at: UTCDateTime,
    ) -> TurnFrame:
        """Atomically build and claim a frame ending at the requested cutoff."""
        with self._signal.locked():
            self._ensure_no_active()
            if self._sealed is None:
                self._sealed = self._build_frame(
                    min(cutoff_seq, self._next_seq), reason, captured_at
                )
            if self._sealed is None:
                raise FrameLifecycleError("no perception writes are available")
            return self.claim(self._sealed.frame_id, turn_id)

    def commit(self, frame_id: EventId, turn_id: TurnId) -> None:
        """Acknowledge and remove only data captured by the active frame."""
        with self._signal.locked():
            claim = self._require_claim(frame_id, turn_id)
            previous = self._persistent_state()
            self._commit(claim.frame)
            try:
                self._persist_pending()
            except Exception:
                self._restore_persistent_state(previous)
                self._active = claim
                raise

    def release(
        self, frame_id: EventId, turn_id: TurnId, reason: str
    ) -> ReleaseDisposition:
        """Replay failures twice, then emit reliable dead-letter evidence."""
        with self._signal.locked():
            claim = self._require_claim(frame_id, turn_id)
            attempts = self._attempts.get(frame_id, 0) + 1
            self._attempts[frame_id] = attempts
            if attempts < 3:
                self._sealed = claim.frame
                self._active = None
                self._signal.bump()
                return ReleaseDisposition.REPLAY
            previous = self._persistent_state()
            if not any(
                isinstance(event, ProcessingFailureEvent)
                for event in claim.frame.events
            ):
                seq = self._allocate_seq()
                failure = self._storage.enqueue_processing_failure(
                    seq=seq,
                    elfie_id=self._elfie_id,
                    failed_frame=claim.frame,
                    reason=reason,
                    occurred_at=self._signal.now(),
                )
                self._ingest.remember(failure, seq)
            self._commit(claim.frame)
            try:
                self._persist_pending()
            except Exception:
                self._restore_persistent_state(previous)
                self._active = claim
                raise
            return ReleaseDisposition.DEAD_LETTERED

    def dead_letters(self) -> Tuple[ProcessingFailureEvent, ...]:
        """Return immutable audit evidence for terminal processing failures."""
        with self._signal.locked():
            return self._storage.dead_letters()

    def wait_for_change(self, deadline: UTCDateTime) -> WaitStatus:
        """Wait for publish/stop until the injected clock reaches a deadline."""
        return self._signal.wait_for_change(deadline)

    def notify_clock_advanced(self) -> None:
        """Wake deadline waiters after a fake or simulation clock advances."""
        self._signal.notify_clock_advanced()

    def stop(self) -> None:
        """Stop ingestion and wake every condition waiter."""
        self._signal.stop()

    def _allocate_seq(self) -> int:
        self._next_seq += 1
        return self._next_seq

    def _build_frame(
        self,
        requested_cutoff: int,
        reason: TriggerReason,
        captured_at: UTCDateTime,
    ) -> Optional[TurnFrame]:
        next_revision = self._frame_revision + 1
        frame = self._storage.build_frame(
            frame_id=EventId(f"frame_{uuid4().hex}"),
            elfie_id=self._elfie_id,
            revision=next_revision,
            requested_cutoff=requested_cutoff,
            frame_event_capacity=self._frame_capacity,
            reason=reason,
            captured_at=captured_at,
        )
        if frame is not None:
            self._frame_revision = next_revision
        return frame

    def _commit(self, frame: TurnFrame) -> None:
        self._storage.commit(frame)
        self._attempts.pop(frame.frame_id, None)
        self._active = None
        self._signal.bump()

    def _persist_pending(self) -> None:
        if self._persistence is not None:
            self._persistence.save_workspace_state(self._persistent_state())

    def _persistent_state(self) -> WorkspacePersistentState:
        return WorkspacePersistentState(
            next_ingest_seq=self._next_seq,
            pending_writes=self._storage.pending_entries(),
            seen_events=self._ingest.entries(),
            loss_records=self._storage.loss_records(),
        )

    def _restore_persistent_state(self, state: WorkspacePersistentState) -> None:
        """Rebuild only uncommitted semantic input; never restore a claimed Run."""
        storage = WorkspaceStorage(
            journal_capacity=self._journal_capacity,
            state_capacity=self._state_capacity,
            media_per_stream_capacity=self._media_capacity,
        )
        ingest = WorkspaceIngestIndex(self._dedupe_capacity)
        for seen in state.seen_events:
            ingest.restore(seen)
        next_seq = state.next_ingest_seq
        for pending in state.pending_writes:
            item = pending.write
            if item.meta.elfie_id != self._elfie_id:
                raise FrameLifecycleError(
                    "durable workspace contains an event for another Elfie"
                )
            if isinstance(item, PerceptionEvent) and storage.journal_full:
                raise FrameLifecycleError(
                    "durable workspace exceeds configured journal capacity"
                )
            seq = pending.ingest_seq
            if ingest.duplicate_seq(item.meta.event_id) is None:
                ingest.remember(item, seq)
            storage.store(item, seq)
        storage.restore_loss_records(state.loss_records)
        self._storage = storage
        self._ingest = ingest
        self._next_seq = next_seq
        self._sealed = None

    def _ensure_no_active(self) -> None:
        if self._active is not None:
            raise ActiveClaimError(self._active.frame.frame_id)

    def _require_claim(self, frame_id: EventId, turn_id: TurnId) -> WorkspaceClaim:
        if self._active is None:
            raise FrameLifecycleError("no frame is currently claimed")
        if self._active.frame.frame_id != frame_id:
            raise FrameLifecycleError("active frame ID does not match")
        if self._active.turn_id != turn_id:
            raise FrameLifecycleError("active turn ID does not match")
        return self._active


__all__ = (
    "ActiveClaimError",
    "FrameLifecycleError",
    "EventWorkspace",
    "ProcessingFailureEvent",
    "ReleaseDisposition",
    "TriggerMetrics",
    "WaitStatus",
)
