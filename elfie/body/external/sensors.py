"""外部身体上报事件的线程安全队列。"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, List

from elfie.body.capabilities import BodyCapabilities
from elfie.body.types import BodyEvent


class ExternalSensors:
    def __init__(self, capabilities: BodyCapabilities):
        self.capabilities = capabilities
        self._events: Deque[BodyEvent] = deque()
        self._lock = Lock()

    def receive(self, event: BodyEvent) -> None:
        if not self.capabilities.supports_sensor(event.sensor):
            return
        with self._lock:
            self._events.append(event)

    def read_events(self) -> List[BodyEvent]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._events)
