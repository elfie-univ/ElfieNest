"""Headless 身体的可注入传感器事件队列。"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any, Deque, List, Mapping, Optional

from elfie.body.types import BodyEvent


class HeadlessSensors:
    def __init__(self, source: str):
        self.source = source
        self._events: Deque[BodyEvent] = deque()
        self._lock = Lock()

    def inject(self, event: BodyEvent) -> None:
        with self._lock:
            self._events.append(event)

    def inject_sensor_data(
        self,
        sensor_data: Mapping[str, Any],
        *,
        event_id: Optional[str] = None,
    ) -> BodyEvent:
        event = BodyEvent(
            sensor="stimulus_bundle",
            payload=dict(sensor_data),
            source=self.source,
            **({"event_id": event_id} if event_id else {}),
        )
        self.inject(event)
        return event

    def read_events(self) -> List[BodyEvent]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._events)
