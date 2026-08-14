"""Actor-scoped typed sensor queue fed directly by the Godot Gateway."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import RLock
from typing import List

from elfie.body.contracts import BodyId, BodySensorEvent, TactileImpact
from elfie.message_types import ActorId, ActorRef, EventId
from infrastructure.godot.gateway.messages import EventName, RuntimeEventFrame


class NativeSensors:
    def __init__(self, body_id: str):
        self.body_id = body_id
        self._events: deque[BodySensorEvent] = deque()
        self._lock = RLock()

    def receive(self, event: RuntimeEventFrame) -> None:
        """Map one validated Body-lane frame without inventing physical values."""
        if (
            event.target_actor_id != self.body_id
            or event.name is not EventName.TACTILE_CONTACT
        ):
            return
        payload = event.payload
        source_semantic_id = str(payload["source_semantic_id"])
        contact_kind = str(payload["contact_kind"])
        intensity_value = payload["intensity"]
        if not isinstance(intensity_value, (int, float)):
            return
        force_value = payload.get("force_newtons")
        force_newtons = (
            float(force_value)
            if isinstance(force_value, (int, float))
            else None
        )
        sensor_event = BodySensorEvent(
            event_id=EventId(event.message_id),
            cause_id=EventId(event.cause_id) if event.cause_id is not None else None,
            body_id=BodyId(self.body_id),
            source=ActorRef(
                actor_id=ActorId(source_semantic_id),
                source_kind="elfie" if contact_kind == "actor" else "world",
            ),
            occurred_at=event.occurred_at,
            received_at=datetime.now(timezone.utc),
            payload=TactileImpact(
                kind="tactile_impact",
                location="body",
                intensity=float(intensity_value),
                direction=str(payload["direction"]),
                contact_kind=contact_kind,
                source_semantic_id=source_semantic_id,
                force_newtons=force_newtons,
            ),
        )
        with self._lock:
            self._events.append(sensor_event)

    def read_sensor_events(self) -> List[BodySensorEvent]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._events)
