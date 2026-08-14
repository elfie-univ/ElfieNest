"""Python-owned semantic random-walk scheduler for Nest Lab."""

from __future__ import annotations

from collections.abc import Iterable
from random import Random
from time import monotonic

from devtools.nest_lab.event_log import LabEventLog
from devtools.nest_lab.models import LabActor
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import CommandName
from nest import Nest

_WANDER_INTERVAL_SECONDS = 2.0


class WanderScheduler:
    """Issue bounded semantic moves without owning any actor decision policy."""

    def __init__(
        self, gateway: GodotAPIServer, nest: Nest, events: LabEventLog
    ) -> None:
        self._gateway = gateway
        self._nest = nest
        self._events = events
        self._active_commands: dict[str, str] = {}
        self._next_command_sequence = 0
        self._next_wander_at = monotonic()
        self._random = Random(7)

    def enable(self) -> None:
        self._next_wander_at = monotonic()

    def resume(self) -> None:
        self._next_wander_at = monotonic()

    def complete(self, command_id: str) -> None:
        self._active_commands.pop(command_id, None)

    def clear(self) -> None:
        self._active_commands.clear()

    def schedule(
        self,
        actors: Iterable[LabActor],
        *,
        ready_revision: int | None,
        enabled: bool,
        paused: bool,
    ) -> None:
        if not enabled or paused or monotonic() < self._next_wander_at:
            return
        self._next_wander_at = monotonic() + _WANDER_INTERVAL_SECONDS
        anchors = self._available_anchors()
        if not anchors or ready_revision is None:
            return
        for actor in actors:
            if actor.actor_id not in self._active_commands.values():
                self._move(actor.actor_id, self._random.choice(anchors), ready_revision)

    def cancel_active(self, ready_revision: int | None) -> None:
        if ready_revision is None:
            return
        for command_id, actor_id in tuple(self._active_commands.items()):
            self._gateway.send_runtime_command(
                CommandName.CANCEL_INTENT,
                {"command_id": command_id, "actor_id": actor_id},
                world_revision=ready_revision,
                cause_id=command_id,
            )

    def _available_anchors(self) -> tuple[str, ...]:
        catalog = self._nest.world_catalog
        return () if catalog is None else tuple(sorted(catalog.anchor_ids))

    def _move(self, actor_id: str, anchor_id: str, ready_revision: int) -> None:
        self._next_command_sequence += 1
        command_id = f"lab-move-{self._next_command_sequence:05d}"
        message_id = self._gateway.send_runtime_command(
            CommandName.EXECUTE_INTENT,
            {
                "command_id": command_id,
                "intent_id": f"{command_id}-intent",
                "actor_id": actor_id,
                "body_generation": 1,
                "initiator": "elfie",
                "intent": "move_to_anchor",
                "anchor_id": anchor_id,
                "deadline_seconds": 10.0,
            },
            world_revision=ready_revision,
            cause_id=command_id,
        )
        if message_id is not None:
            self._active_commands[command_id] = actor_id
            self._events.append("wander_move", f"{actor_id} -> {anchor_id}")
