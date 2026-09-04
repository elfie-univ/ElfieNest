"""外部身体上报事件的线程安全队列。"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Iterable, List

from elfie.body.capabilities import BodyCapabilities
from elfie.body.contracts import (
    ActionOutcomePayload,
    BodySensorEvent,
    NestFactNoticePayload,
    SemanticActionResultPayload,
    sensor_capability_for_payload,
)


class ExternalSensors:
    def __init__(self, capabilities: BodyCapabilities):
        self.capabilities = capabilities
        self._sensor_events: Deque[BodySensorEvent] = deque()
        self._lock = Lock()

    def receive(self, event: BodySensorEvent) -> None:
        if not self._accepts(event):
            return
        with self._lock:
            self._sensor_events.append(event)

    def read_sensor_events(self) -> List[BodySensorEvent]:
        with self._lock:
            events = list(self._sensor_events)
            self._sensor_events.clear()
        return events

    def ingest(self, events: Iterable[BodySensorEvent]) -> None:
        with self._lock:
            for event in events:
                if self._accepts(event):
                    self._sensor_events.append(event)

    def _accepts(self, event: BodySensorEvent) -> bool:
        payload = event.payload
        # Nest semantic facts and terminal Body feedback already passed their
        # authority checks; they are not physical sensor names.
        if isinstance(
            payload,
            (ActionOutcomePayload, SemanticActionResultPayload, NestFactNoticePayload),
        ):
            return True
        capability = sensor_capability_for_payload(payload)
        if capability is not None and self.capabilities.supports_sensor(capability):
            return True
        # Pre-catalog external adapters may still expose raw event kinds.  An
        # explicit catalog remains authoritative inside BodyCapabilities.
        return self.capabilities.supports_sensor(payload.kind)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._sensor_events)
