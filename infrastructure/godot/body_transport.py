"""Thread-safe Body command bridge to the authoritative Godot Runtime."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Condition
from typing import Literal, Optional, Protocol, TypedDict, cast

from infrastructure.godot.gateway.messages import RuntimeEventFrame


class RuntimeIntentPayload(TypedDict, total=False):
    command_id: str
    intent_id: str
    actor_id: str
    body_generation: int
    initiator: Literal["elfie"]
    intent: str
    anchor_id: str
    text: str
    expression: str
    observation_id: str
    max_results: int
    distance: float
    angle_degrees: float
    intensity: float
    deadline_seconds: float
    speech_profile: str
    emotion: str


class GodotGateway(Protocol):
    """Runtime operations required by a native Body."""

    def send_body_command(
        self,
        payload: RuntimeIntentPayload,
        *,
        cause_id: str,
    ) -> bool: ...

    def cancel_body_command(
        self,
        *,
        command_id: str,
        actor_id: str,
    ) -> bool: ...

    def register_body_sink(self, actor_id: str, sink: GodotTransport) -> None: ...

    def unregister_body_sink(self, actor_id: str, sink: GodotTransport) -> None: ...


NativeEventHandler = Callable[[RuntimeEventFrame], None]
SemanticActionResolver = Callable[[RuntimeIntentPayload], Optional[str]]
VisualObservationRequester = Callable[[RuntimeIntentPayload], bool]


@dataclass(frozen=True)
class RuntimeIntentResult:
    statuses: tuple[str, ...]
    terminal_status: str
    reason: str = ""
    events: tuple[RuntimeEventFrame, ...] = ()


@dataclass
class _PendingIntent:
    actor_id: str
    statuses: list[str] = field(default_factory=list)
    terminal_status: str | None = None
    reason: str = ""
    events: list[RuntimeEventFrame] = field(default_factory=list)


class GodotTransport:
    """Wait for actual Runtime terminal events without blocking the Nest tick."""

    def __init__(
        self,
        gateway: GodotGateway,
        *,
        actor_id: str,
        speech_intent: Callable[[RuntimeIntentPayload], bool] | None = None,
        semantic_action: SemanticActionResolver | None = None,
        semantic_action_result: Callable[
            [RuntimeIntentPayload, RuntimeIntentResult], None
        ]
        | None = None,
        visual_observation: VisualObservationRequester | None = None,
    ):
        self.gateway = gateway
        self.actor_id = actor_id
        self._handlers: list[NativeEventHandler] = []
        self._pending: dict[str, _PendingIntent] = {}
        self._condition = Condition()
        self._speech_intent = speech_intent
        self._semantic_action = semantic_action
        self._semantic_action_result = semantic_action_result
        self._visual_observation = visual_observation

    def request_visual_observation(self, payload: RuntimeIntentPayload) -> bool:
        """Delegate semantic vision requests to Nest before they reach Godot."""
        if self._visual_observation is None:
            return False
        return bool(self._visual_observation(payload))

    def connect(self, handler: NativeEventHandler) -> None:
        with self._condition:
            if handler in self._handlers:
                return
            if not self._handlers:
                self.gateway.register_body_sink(self.actor_id, self)
            self._handlers.append(handler)

    def disconnect(self, handler: NativeEventHandler) -> None:
        with self._condition:
            if handler not in self._handlers:
                return
            self._handlers.remove(handler)
            if not self._handlers:
                self.gateway.unregister_body_sink(self.actor_id, self)

    def execute_intent(
        self,
        payload: RuntimeIntentPayload,
        *,
        timeout_seconds: float,
    ) -> RuntimeIntentResult:
        command_id = payload["command_id"]
        actor_id = payload["actor_id"]
        with self._condition:
            if command_id in self._pending:
                return RuntimeIntentResult((), "failed", "duplicate_command_id")
            self._pending[command_id] = _PendingIntent(actor_id=actor_id)
        wire_payload = cast(RuntimeIntentPayload, dict(payload))
        semantic_target = payload.get("anchor_id")
        semantic_action_requested = (
            payload.get("intent") == "move_to_anchor"
            and isinstance(semantic_target, str)
            and (
                semantic_target in {"home", "my_home"}
                or semantic_target.startswith("facility/")
            )
        )
        if semantic_action_requested:
            if self._semantic_action is None:
                with self._condition:
                    self._pending.pop(command_id, None)
                return RuntimeIntentResult((), "failed", "semantic_action_unavailable")
            resolved_anchor_id = self._semantic_action(payload)
            if resolved_anchor_id is None:
                with self._condition:
                    self._pending.pop(command_id, None)
                return RuntimeIntentResult((), "failed", "semantic_target_unavailable")
            wire_payload["anchor_id"] = resolved_anchor_id
        if payload.get("intent") == "speak":
            if self._speech_intent is not None and not self._speech_intent(payload):
                with self._condition:
                    self._pending.pop(command_id, None)
                return RuntimeIntentResult((), "failed", "speech_reach_unavailable")
            wire_payload.pop("text", None)
            wire_payload.pop("emotion", None)
        if not self.gateway.send_body_command(
            wire_payload,
            cause_id=command_id,
        ):
            with self._condition:
                self._pending.pop(command_id, None)
            result = RuntimeIntentResult((), "failed", "runtime_not_ready")
            if semantic_action_requested and self._semantic_action_result is not None:
                self._semantic_action_result(payload, result)
            return result

        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        with self._condition:
            pending = self._pending[command_id]
            while pending.terminal_status is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    self.gateway.cancel_body_command(
                        command_id=command_id,
                        actor_id=actor_id,
                    )
                    pending.terminal_status = "timed_out"
                    pending.reason = "runtime command deadline exceeded"
                    break
                self._condition.wait(timeout=remaining)
            result = RuntimeIntentResult(
                statuses=tuple(pending.statuses),
                terminal_status=pending.terminal_status,
                reason=pending.reason,
                events=tuple(pending.events),
            )
            self._pending.pop(command_id, None)
            if semantic_action_requested and self._semantic_action_result is not None:
                self._semantic_action_result(payload, result)
            return result

    def receive_runtime_event(
        self,
        event: RuntimeEventFrame,
    ) -> None:
        if event.target_actor_id != self.actor_id:
            return
        event_name = event.name.value
        payload = event.payload
        command_id_value = payload.get("command_id")
        with self._condition:
            if isinstance(command_id_value, str):
                pending = self._pending.get(command_id_value)
                if pending is not None and pending.terminal_status is None:
                    pending.events.append(event)
                    if event_name == "intent_accepted":
                        self._append_status(pending, "accepted")
                    elif event_name == "intent_started":
                        self._append_status(pending, "started")
                    elif event_name == "intent_terminal":
                        status = payload.get("status")
                        if isinstance(status, str):
                            pending.terminal_status = status
                            reason = payload.get("reason")
                            pending.reason = reason if isinstance(reason, str) else ""
                            self._condition.notify_all()
            handlers = tuple(self._handlers)
        for handler in handlers:
            handler(event)

    def interrupt_pending(self, reason: str = "runtime disconnected") -> None:
        with self._condition:
            for pending in self._pending.values():
                if pending.terminal_status is None:
                    pending.terminal_status = "interrupted"
                    pending.reason = reason
            self._condition.notify_all()

    def cancel_all(self, *, actor_id: str) -> None:
        with self._condition:
            command_ids = [
                command_id
                for command_id, pending in self._pending.items()
                if pending.actor_id == actor_id and pending.terminal_status is None
            ]
            for command_id in command_ids:
                pending = self._pending[command_id]
                pending.terminal_status = "cancelled"
                pending.reason = "actor commands cancelled"
            if command_ids:
                self._condition.notify_all()
        for command_id in command_ids:
            self.gateway.cancel_body_command(
                command_id=command_id,
                actor_id=actor_id,
            )

    @staticmethod
    def _append_status(pending: _PendingIntent, status: str) -> None:
        if status not in pending.statuses:
            pending.statuses.append(status)


__all__ = (
    "GodotGateway",
    "GodotTransport",
    "RuntimeIntentPayload",
    "RuntimeIntentResult",
)
