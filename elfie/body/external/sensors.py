"""外部身体上报事件的线程安全队列。"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, List

from elfie.body.capabilities import BodyCapabilities
from elfie.body.contracts import BodySensorEvent


class ExternalSensors:
    def __init__(self, capabilities: BodyCapabilities):
        self.capabilities = capabilities
        self._sensor_events: Deque[BodySensorEvent] = deque()
        self._lock = Lock()

    def receive(self, event: BodySensorEvent) -> None:
        if not self.capabilities.supports_sensor(event.payload.kind):
            return
        with self._lock:
            self._sensor_events.append(event)

    def read_sensor_events(self) -> List[BodySensorEvent]:
        with self._lock:
            events = list(self._sensor_events)
            self._sensor_events.clear()
        return events

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._sensor_events)
