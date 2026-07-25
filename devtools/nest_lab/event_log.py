"""Bounded in-memory timeline used only by the Nest Lab."""

from __future__ import annotations

from collections import deque

from devtools.nest_lab.models import LabEvent


class LabEventLog:
    """Keep the latest developer-visible events without persistence."""

    def __init__(self, capacity: int = 200) -> None:
        self._capacity = capacity
        self._sequence = 0
        self._events: deque[LabEvent] = deque(maxlen=capacity)

    def append(self, name: str, detail: str) -> None:
        """Append one normalized event."""
        self._sequence += 1
        self._events.append(LabEvent(self._sequence, name, detail))

    def items(self) -> tuple[LabEvent, ...]:
        """Return events in display order."""
        return tuple(self._events)
