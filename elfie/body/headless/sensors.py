"""Headless 身体的可注入传感器事件队列。"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, List

from elfie.body.contracts import BodySensorEvent


class HeadlessSensors:
    def __init__(self, source: str):
        self.source = source
        self._sensor_events: Deque[BodySensorEvent] = deque()
        self._lock = Lock()

    def inject_event(self, event: BodySensorEvent) -> None:
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
