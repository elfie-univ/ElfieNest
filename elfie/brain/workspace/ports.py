"""Structural Brain workspace ports that hide queue and storage internals."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from elfie.brain.workspace.contracts import (
    IngestReceipt,
    PerceptionWrite,
    TriggerReason,
    TurnFrame,
    WorkspacePersistentState,
)
from elfie.message_types import EventId, TurnId, UTCDateTime


@runtime_checkable
class PerceptionSink(Protocol):
    """Write-only perception capability exposed to producer adapters."""

    def publish(self, item: PerceptionWrite) -> IngestReceipt:
        """Publish one typed write and return its observable disposition."""
        ...


@runtime_checkable
class WorkspacePersistencePort(Protocol):
    """Atomically persist pending input and the bounded dedupe frontier."""

    def load_workspace_state(self) -> WorkspacePersistentState:
        """Return the complete restart-safe pre-Run workspace state."""
        ...

    def save_workspace_state(self, state: WorkspacePersistentState) -> None:
        """Replace pending input and dedupe state in one atomic write."""
        ...


@runtime_checkable
class TurnFrameSource(Protocol):
    """Coordinator-only frame lifecycle capability."""

    def seal(
        self,
        *,
        reason: TriggerReason,
        captured_at: UTCDateTime,
    ) -> Optional[EventId]:
        """Seal the current cutoff and return its frame ID, if non-empty."""
        ...

    def claim(self, frame_id: EventId, turn_id: TurnId) -> TurnFrame:
        """Claim one sealed frame for a reasoning turn."""
        ...

    def commit(self, frame_id: EventId, turn_id: TurnId) -> None:
        """Commit a successfully completed frame claim."""
        ...

    def release(self, frame_id: EventId, turn_id: TurnId, reason: str) -> None:
        """Release a failed claim so the frame can be replayed."""
        ...


__all__ = ("PerceptionSink", "TurnFrameSource", "WorkspacePersistencePort")
