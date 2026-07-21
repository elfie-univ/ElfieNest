"""Locking, revision notification, and deterministic waits for a workspace."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Condition, RLock

from elfie.brain.workspace_types import WaitStatus
from elfie.message_types import UTCDateTime

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceSignal:
    """Own the workspace lock and its change/stop condition state."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._condition = Condition(RLock())
        self._revision = 0
        self._stopped = False

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def stopped(self) -> bool:
        return self._stopped

    def now(self) -> datetime:
        return self._clock()

    def locked(self) -> Condition:
        """Hold the shared workspace lock across one atomic operation."""
        return self._condition

    def bump(self) -> None:
        """Record an observable mutation and wake all waiters."""
        self._revision += 1
        self._condition.notify_all()

    def wait_for_change(self, deadline: UTCDateTime) -> WaitStatus:
        """Wait until a revision change, stop, or injected-clock deadline."""
        with self._condition:
            revision = self._revision
            while True:
                if self._stopped:
                    return WaitStatus.STOPPED
                if self._revision != revision:
                    return WaitStatus.CHANGED
                remaining = (deadline - self._clock()).total_seconds()
                if remaining <= 0:
                    return WaitStatus.TIMED_OUT
                self._condition.wait(timeout=remaining)

    def notify_clock_advanced(self) -> None:
        """Wake waiters so an injected clock deadline can be re-evaluated."""
        with self._condition:
            self._condition.notify_all()

    def stop(self) -> None:
        """Reject future ingestion and wake every waiter."""
        with self._condition:
            self._stopped = True
            self.bump()


__all__ = ("Clock", "WorkspaceSignal", "utc_now")
