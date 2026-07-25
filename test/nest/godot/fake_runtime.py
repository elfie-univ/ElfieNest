"""Deterministic in-process protocol v2 Runtime used by contract tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from nest.godot.messages import (
    CommandName,
    EventName,
    JsonObject,
    RuntimeEventFrame,
)
from nest.godot.session import RuntimeConnection


class FakeRuntime:
    """Execute the v2 ordering contract without pretending to model geometry."""

    def __init__(self) -> None:
        self.runtime_connection: Optional[RuntimeConnection] = None
        self.commands: List[Tuple[CommandName, JsonObject, int]] = []
        self.actor_ids: Tuple[str, ...] = ()
        self._events: List[RuntimeEventFrame] = []
        self._generation = 0
        self._revision = 0
        self._sequence = 0

    def connect(self, runtime_id: str = "fake-runtime") -> RuntimeConnection:
        self._generation += 1
        self.runtime_connection = RuntimeConnection(runtime_id, self._generation)
        return self.runtime_connection

    def disconnect(self) -> None:
        self.runtime_connection = None

    def mark_runtime_ready(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None:
        if connection == self.runtime_connection:
            self._revision = world_revision

    def send_runtime_command(
        self,
        name: CommandName,
        payload: JsonObject,
        *,
        world_revision: int,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        connection = self.runtime_connection
        if connection is None:
            return None
        self.commands.append((name, payload, world_revision))
        command_id = correlation_id or f"fake-command-{len(self.commands)}"
        if name is CommandName.CONFIGURE_WORLD:
            self._revision = world_revision
            self._emit(EventName.SCENE_MANIFEST, self._manifest(payload), command_id)
            self._emit(EventName.WORLD_READY, {"ready": True}, command_id)
        elif name is CommandName.SYNC_ACTORS:
            raw_actors = payload.get("actors", [])
            actors = raw_actors if isinstance(raw_actors, list) else []
            self.actor_ids = tuple(
                sorted(
                    str(actor["actor_id"])
                    for actor in actors
                    if isinstance(actor, dict) and "actor_id" in actor
                )
            )
            self._emit(EventName.WORLD_SNAPSHOT, self._snapshot(), command_id)
        elif name is CommandName.EXECUTE_INTENT:
            progress = {
                "command_id": str(payload["command_id"]),
                "actor_id": str(payload["actor_id"]),
            }
            self._emit(EventName.INTENT_ACCEPTED, progress, command_id)
            self._emit(EventName.INTENT_STARTED, progress, command_id)
            terminal = {**progress, "status": "completed", "detail": "contract_only"}
            self._emit(EventName.INTENT_TERMINAL, terminal, command_id)
        elif name is CommandName.CANCEL_INTENT:
            terminal = dict(payload)
            terminal["status"] = "cancelled"
            self._emit(EventName.INTENT_TERMINAL, terminal, command_id)
        return command_id

    def send_body_command(
        self,
        payload: Dict[str, object],
        *,
        correlation_id: str,
    ) -> bool:
        return (
            self.send_runtime_command(
                CommandName.EXECUTE_INTENT,
                payload,
                world_revision=self._revision,
                correlation_id=correlation_id,
            )
            is not None
        )

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        return (
            self.send_runtime_command(
                CommandName.CANCEL_INTENT,
                {"command_id": command_id, "actor_id": actor_id},
                world_revision=self._revision,
                correlation_id=command_id,
            )
            is not None
        )

    def drain_runtime_events(self) -> Tuple[RuntimeEventFrame, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    def _emit(
        self,
        name: EventName,
        payload: JsonObject,
        correlation_id: str,
    ) -> None:
        connection = self.runtime_connection
        if connection is None:
            return
        self._sequence += 1
        self._events.append(
            RuntimeEventFrame(
                protocol=2,
                kind="event",
                name=name,
                message_id=f"fake-event-{self._sequence}",
                runtime_id=connection.runtime_id,
                generation=connection.generation,
                world_revision=self._revision,
                occurred_at=datetime.now(timezone.utc),
                correlation_id=correlation_id,
                payload=payload,
            )
        )

    def _manifest(self, config: JsonObject) -> JsonObject:
        raw_bed_count = config.get("bed_count", 4)
        bed_count = int(raw_bed_count) if isinstance(raw_bed_count, int) else 4
        return {
            "nest_id": str(config.get("nest_id", "local-nest")),
            "world_revision": self._revision,
            "bed_count": bed_count,
            "zones": [
                {
                    "zone_id": "dorm-01",
                    "kind": "dorm",
                    "label": "01 宿舍",
                    "stable_order": 0,
                    "active": True,
                }
            ],
            "anchors": [
                {
                    "anchor_id": f"dorm-01/bed-{index:02d}",
                    "zone_id": "dorm-01",
                    "kind": "bed",
                    "label": f"床位 {index:02d}",
                    "stable_order": index - 1,
                    "active": True,
                }
                for index in range(1, bed_count + 1)
            ],
        }

    def _snapshot(self) -> JsonObject:
        return {
            "world_revision": self._revision,
            "actors": [
                {
                    "actor_id": actor_id,
                    "zone_id": "dorm-01",
                    "posture": "idle",
                    "active_command_id": None,
                }
                for actor_id in self.actor_ids
            ],
        }


__all__ = ("FakeRuntime",)
