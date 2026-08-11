"""Native 身体从 Godot 接收的传感器事件队列。"""

from __future__ import annotations

from typing import Any, Dict, List

from elfie.body.contracts import BodySensorEvent


class NativeSensors:
    def __init__(self, body_id: str):
        self.body_id = body_id

    def receive(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Runtime v2 physical perceptions are delivered by Nest orchestration."""
        _ = event_name, payload

    def read_sensor_events(self) -> List[BodySensorEvent]:
        return []

    @property
    def pending_count(self) -> int:
        return 0
