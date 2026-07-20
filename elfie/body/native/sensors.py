"""Native 身体从 Godot 接收的传感器事件队列。"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, List

from elfie.body.types import BodyEvent


class NativeSensors:
    def __init__(self, body_id: str):
        self.body_id = body_id
        self._events: Deque[BodyEvent] = deque()
        self._lock = Lock()

    def receive(self, event_name: str, payload: Dict[str, Any]) -> None:
        """把现有 Godot 入站事件转成神经系统已经理解的字段。"""
        if event_name == "runtime_ready":
            return
        if payload.get("elfie_id") != self.body_id:
            return

        event = self._convert(event_name, payload)
        if event is None:
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

    def _convert(
        self, event_name: str, payload: Dict[str, Any]
    ) -> BodyEvent | None:
        if event_name == "user_message":
            message = str(payload.get("message", ""))
            if not message:
                return None
            sensor_data: Dict[str, Any] = {
                "has_new_message": True,
                "user_message": message,
            }
            if payload.get("message_id") is not None:
                sensor_data["message_id"] = payload["message_id"]
            return BodyEvent(
                sensor="hearing",
                payload=sensor_data,
                source="godot:user_message",
            )

        if event_name == "arrived_at":
            return BodyEvent(
                sensor="proprioception",
                payload={
                    "has_arrival_update": True,
                    "arrived_at": True,
                    "target": str(payload.get("target", "")),
                    "posture": str(payload.get("posture", "")),
                },
                source="godot:arrived_at",
            )
        return None
