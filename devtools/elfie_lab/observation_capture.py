"""Capture proxy that keeps the single-sink contract while recording events.

The Lab session wraps the caller-supplied ``BrainObservationSink`` (or a
missing one) in this thin proxy before wiring the Brain, so every
``run_turn`` can hand the trace projection exactly the envelopes emitted
during that turn.  The proxy only forwards and records; it never filters,
transforms or interprets observations.
"""

from __future__ import annotations

import threading
from typing import List, Optional, Tuple

from elfie.brain.observation import BrainObservation, BrainObservationSink


class CapturingObservationSink:
    """Forward every event to the wrapped sink and record it locally.

    ``downstream`` may be ``None``: the Brain then behaves exactly as when
    no consumer sink was wired, while the Lab still collects the envelopes
    it needs for its own read-only projection.
    """

    def __init__(self, downstream: Optional[BrainObservationSink] = None) -> None:
        self._downstream = downstream
        self._lock = threading.Lock()
        self._events: List[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)
        downstream = self._downstream
        if downstream is not None:
            try:
                downstream.emit(event)
            except Exception:  # noqa: BLE001 - collection must never affect the Brain
                return

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        """Return the events recorded so far, in emit order."""
        with self._lock:
            return tuple(self._events)

    def clear(self) -> None:
        """Drop all recorded events (called before each turn window)."""
        with self._lock:
            self._events.clear()
