"""Manual controls for the disposable Lab, using established Runtime commands."""

from __future__ import annotations

from collections.abc import Collection

from devtools.nest_lab.event_log import LabEventLog
from devtools.nest_lab.models import LabActionRequest, NestLabConflictError
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import CommandName, JsonObject
from nest import Nest


class LabActions:
    def __init__(
        self, gateway: GodotAPIServer, nest: Nest, events: LabEventLog
    ) -> None:
        self._gateway = gateway
        self._nest = nest
        self._events = events
        self._sequence = 0
        self._active: dict[str, str] = {}
        self._pending: dict[str, tuple[JsonObject, int]] = {}

    def targets(self) -> list[dict[str, str | None]]:
        catalog = self._nest.world_catalog
        if catalog is None:
            return []
        return [
            {
                "anchor_id": anchor.anchor_id,
                "kind": anchor.kind.value,
                "label": f"{zone.label} · {anchor.label}",
                "owner_id": self._nest.home_occupant(anchor.anchor_id),
            }
            for zone in catalog.zones
            for anchor in zone.anchors
            if anchor.active
        ]

    def execute(
        self,
        request: LabActionRequest,
        actor_ids: Collection[str],
        revision: int | None,
    ) -> dict[str, str]:
        if request.actor_id not in actor_ids:
            raise NestLabConflictError("请选择当前实验中的角色")
        if revision is None:
            raise NestLabConflictError("世界尚未就绪，请等待 Godot 完成加载")
        intent = "emotion_expression"
        target: JsonObject = {"expression": request.animation}
        if request.action != "animation":
            anchor = next(
                (
                    item
                    for item in self.targets()
                    if item["anchor_id"] == request.anchor_id
                ),
                None,
            )
            if anchor is None:
                raise NestLabConflictError("目标不在当前场景目录中")
            if request.action == "use" and anchor["kind"] not in {"bed", "chair"}:
                raise NestLabConflictError("请选择可坐的座位或床位")
            intent = "move_to_anchor" if request.action == "move" else "use_anchor"
            target = {"anchor_id": request.anchor_id}
        if request.furniture_cycle is not None:
            kind = next(
                item["kind"]
                for item in self.targets()
                if item["anchor_id"] == request.anchor_id
            )
            if (request.furniture_cycle == "seat") != (kind == "chair"):
                raise NestLabConflictError("坐姿流程请选择座位，睡眠流程请选择床位")
            target["furniture_cycle"] = request.furniture_cycle
        self._sequence += 1
        command_id = f"lab-action-{self._sequence:05d}"
        payload: JsonObject = {
            "command_id": command_id,
            "intent_id": f"{command_id}-intent",
            "actor_id": request.actor_id,
            "body_generation": 1,
            "initiator": "elfie",
            "intent": intent,
            "deadline_seconds": 120.0,
            **target,
        }
        previous = self._active.get(request.actor_id)
        if previous is not None:
            already_cancelling = request.actor_id in self._pending
            self._pending[request.actor_id] = (payload, revision)
            if not already_cancelling:
                sent = self._gateway.send_runtime_command(
                    CommandName.CANCEL_INTENT,
                    {"actor_id": request.actor_id, "command_id": previous},
                    world_revision=revision,
                    cause_id=previous,
                )
                if sent is None:
                    self._pending.pop(request.actor_id, None)
                    raise NestLabConflictError("Godot 已断开，取消动作未发送")
            self._events.append(
                "action_switch_pending",
                f"{request.actor_id}: {previous} → {command_id}",
            )
        else:
            self._dispatch(payload, revision)
        return {"command_id": command_id, "actor_id": request.actor_id}

    def _dispatch(self, payload: JsonObject, revision: int) -> None:
        actor_id = str(payload["actor_id"])
        command_id = str(payload["command_id"])
        self._active[actor_id] = command_id
        message_id = self._gateway.send_runtime_command(
            CommandName.EXECUTE_INTENT,
            payload,
            world_revision=revision,
            cause_id=command_id,
        )
        if message_id is None:
            self._active.pop(actor_id, None)
            raise NestLabConflictError("Godot 已断开，动作未发送")

    def stop(
        self, actor_id: str, actor_ids: Collection[str], revision: int | None
    ) -> dict[str, str]:
        return self.execute(
            LabActionRequest(actor_id=actor_id, action="animation", animation="idle"),
            actor_ids,
            revision,
        )

    def remove_actor(self, actor_id: str, revision: int | None) -> None:
        """Cancel a removed or regenerated actor without starting another intent."""
        self._pending.pop(actor_id, None)
        command_id = self._active.pop(actor_id, None)
        if command_id is not None and revision is not None:
            self._gateway.send_runtime_command(
                CommandName.CANCEL_INTENT,
                {"actor_id": actor_id, "command_id": command_id},
                world_revision=revision,
                cause_id=command_id,
            )

    def complete(self, payload: JsonObject) -> None:
        actor_id = str(payload.get("actor_id", ""))
        if self._active.get(actor_id) == payload.get("command_id"):
            self._active.pop(actor_id, None)
            pending = self._pending.pop(actor_id, None)
            if pending is not None:
                try:
                    self._dispatch(*pending)
                except NestLabConflictError as error:
                    self._events.append("action_switch_failed", str(error))

    def stop_all(self, actor_ids: Collection[str], revision: int | None) -> None:
        if revision is not None:
            for actor_id in tuple(actor_ids):
                self.stop(actor_id, actor_ids, revision)

    def clear(self) -> None:
        self._active.clear()
        self._pending.clear()
