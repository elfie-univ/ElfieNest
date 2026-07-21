"""Thread-safe MPSC workspace and reliable perception-frame lifecycle."""

from __future__ import annotations

from typing import Optional, Tuple
from uuid import uuid4

from elfie.brain.perception_types import (
    IngestDisposition,
    IngestReceipt,
    PerceptionEvent,
    PerceptionFrame,
    PerceptionWrite,
    ProcessingFailureEvent,
    TriggerReason,
)
from elfie.brain.workspace_ingest import WorkspaceIngestIndex
from elfie.brain.workspace_signal import Clock, WorkspaceSignal, utc_now
from elfie.brain.workspace_storage import WorkspaceStorage
from elfie.brain.workspace_types import (
    ActiveClaimError,
    FrameLifecycleError,
    TriggerMetrics,
    WaitStatus,
    WorkspaceClaim,
)
from elfie.message_types import ElfieId, EventId, TurnId, UTCDateTime


class PerceptualWorkspace:
    """Four-zone MPSC workspace with claim, replay, and commit semantics."""

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
    ) -> None:
        if frame_event_capacity < 1:
            raise FrameLifecycleError("frame event capacity must be positive")
        self._elfie_id = elfie_id
        self._frame_capacity = frame_event_capacity
        self._signal = WorkspaceSignal(clock)
        self._storage = WorkspaceStorage(
            journal_capacity=journal_capacity,
            state_capacity=state_capacity,
            media_per_stream_capacity=media_per_stream_capacity,
        )
        self._ingest = WorkspaceIngestIndex(dedupe_capacity)
        self._sealed: Optional[PerceptionFrame] = None
        self._active: Optional[WorkspaceClaim] = None
        self._attempts: dict[EventId, int] = {}
        self._next_seq = 0
        self._frame_revision = 0

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
            duplicate_seq = self._ingest.duplicate_seq(event_id)
            if duplicate_seq is not None:
                return self._ingest.receipt(
                    event_id,
                    IngestDisposition.DUPLICATE,
                    duplicate_seq,
                    False,
                    "duplicate",
                )
            if isinstance(item, PerceptionEvent) and self._storage.journal_full:
                return self._ingest.receipt(
                    event_id,
                    IngestDisposition.BACKPRESSURED,
                    None,
                    True,
                    "journal_capacity",
                )
            seq = self._allocate_seq()
            disposition = self._storage.store(item, seq)
            self._ingest.remember(event_id, seq)
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

    def claim(self, frame_id: EventId, turn_id: TurnId) -> PerceptionFrame:
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
    ) -> PerceptionFrame:
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
            self._commit(claim.frame)

    def release(self, frame_id: EventId, turn_id: TurnId, reason: str) -> None:
        """Replay failures twice, then emit reliable dead-letter evidence."""
        with self._signal.locked():
            claim = self._require_claim(frame_id, turn_id)
            attempts = self._attempts.get(frame_id, 0) + 1
            self._attempts[frame_id] = attempts
            if attempts < 3:
                self._sealed = claim.frame
                self._active = None
                self._signal.bump()
                return
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
                self._ingest.remember(failure.meta.event_id, seq)
            self._commit(claim.frame)

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
    ) -> Optional[PerceptionFrame]:
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

    def _commit(self, frame: PerceptionFrame) -> None:
        self._storage.commit(frame.cutoff_seq)
        self._attempts.pop(frame.frame_id, None)
        self._active = None
        self._signal.bump()

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
    "PerceptualWorkspace",
    "ProcessingFailureEvent",
    "TriggerMetrics",
    "WaitStatus",
)
