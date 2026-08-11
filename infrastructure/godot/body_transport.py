"""Thread-safe Body command bridge to the authoritative Godot Runtime."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Condition
from typing import Protocol, TypedDict


class RuntimeIntentPayload(TypedDict, total=False):
    command_id: str
    actor_id: str
    intent: str
    anchor_id: str
    text: str
    expression: str
    deadline_seconds: float


class GodotGateway(Protocol):
    """Runtime operations required by a native Body."""

    def send_body_command(
        self,
        payload: RuntimeIntentPayload,
        *,
        correlation_id: str,
    ) -> bool: ...

    def cancel_body_command(
        self,
        *,
        command_id: str,
        actor_id: str,
    ) -> bool: ...


NativeEventHandler = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True)
class RuntimeIntentResult:
    statuses: tuple[str, ...]
    terminal_status: str
    reason: str = ""


@dataclass
class _PendingIntent:
    actor_id: str
    statuses: list[str] = field(default_factory=list)
    terminal_status: str | None = None
    reason: str = ""


class GodotTransport:
    """Wait for actual Runtime terminal events without blocking the Nest tick."""

    def __init__(self, gateway: GodotGateway):
        self.gateway = gateway
        self._handlers: list[NativeEventHandler] = []
        self._pending: dict[str, _PendingIntent] = {}
        self._condition = Condition()

    def connect(self, handler: NativeEventHandler) -> None:
        if handler not in self._handlers:
            self._handlers.append(handler)

    def disconnect(self, handler: NativeEventHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

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
        if not self.gateway.send_body_command(
            payload,
            correlation_id=command_id,
        ):
            with self._condition:
                self._pending.pop(command_id, None)
            return RuntimeIntentResult((), "failed", "runtime_not_ready")

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
            )
            self._pending.pop(command_id, None)
            return result

    def receive_runtime_event(
        self,
        event_name: str,
        payload: dict[str, object],
    ) -> None:
        command_id_value = payload.get("command_id")
        if not isinstance(command_id_value, str):
            return
        with self._condition:
            pending = self._pending.get(command_id_value)
            if pending is None or pending.terminal_status is not None:
                return
            if event_name == "intent_accepted":
                self._append_status(pending, "accepted")
            elif event_name == "intent_started":
                self._append_status(pending, "started")
            elif event_name == "intent_terminal":
                status = payload.get("status")
                if not isinstance(status, str):
                    return
                pending.terminal_status = status
                reason = payload.get("reason")
                pending.reason = reason if isinstance(reason, str) else ""
                self._condition.notify_all()

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
