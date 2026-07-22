"""Native 身体从 Godot 接收的传感器事件队列。"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Dict, List
from uuid import uuid4

from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    ProprioceptionSample,
)
from elfie.message_types import ActorId, ActorRef, EventId


class NativeSensors:
    def __init__(self, body_id: str):
        self.body_id = body_id
        self._sensor_events: Deque[BodySensorEvent] = deque()
        self._lock = Lock()

    def receive(self, event_name: str, payload: Dict[str, Any]) -> None:
        """把现有 Godot 入站事件转成神经系统已经理解的字段。"""
        if event_name == "runtime_ready":
            return
        if payload.get("elfie_id") != self.body_id:
            return

        sensor_event = self._convert_typed(event_name, payload)
        if sensor_event is None:
            return
        with self._lock:
            self._sensor_events.append(sensor_event)

    def read_sensor_events(self) -> List[BodySensorEvent]:
        with self._lock:
            events = list(self._sensor_events)
            self._sensor_events.clear()
        return events

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._sensor_events)

    def _convert_typed(
        self,
        event_name: str,
        payload: Dict[str, Any],
    ) -> BodySensorEvent | None:
        now = datetime.now(timezone.utc)
        actor_id = ActorId(str(payload.get("actor_id", "godot-user")))
        source = ActorRef(actor_id=actor_id, source_kind=f"godot:{event_name}")
        event_id = EventId(
            str(payload.get("message_id") or f"event_{uuid4().hex}")
        )
        occurred_at = payload.get("occurred_at")
        event_time = occurred_at if isinstance(occurred_at, datetime) else now
        if event_name == "arrived_at":
            event_payload = ProprioceptionSample(
                kind="proprioception_sample",
                posture=str(payload.get("posture") or "unknown"),
                target=str(payload["target"]) if payload.get("target") else None,
                arrived=True,
            )
        else:
            return None
        return BodySensorEvent(
            event_id=event_id,
            body_id=BodyId(self.body_id),
            source=source,
            occurred_at=event_time,
            received_at=now,
            payload=event_payload,
        )
