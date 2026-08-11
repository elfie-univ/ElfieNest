from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any, Dict, List

from elfie.body import (
    BodyId,
    BodyMode,
    BodyPort,
    CommandStatus,
    EmergencyStopCommand,
    ExpressionCommand,
    MotionCommand,
    SpeechCommand,
)
from elfie.message_types import CommandId, IntentId, TurnId
from infrastructure.godot import GodotTransport, NativeBody

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


class FakeGodotGateway:
    def __init__(self) -> None:
        self.sent: List[Dict[str, Any]] = []
        self.cancelled: List[Dict[str, str]] = []
        self.transport: GodotTransport | None = None
        self.auto_complete = True
        self.command_sent = Event()

    def send_body_command(
        self,
        payload: Dict[str, Any],
        *,
        correlation_id: str,
    ) -> bool:
        self.sent.append({"action": "execute_intent", "payload": payload})
        self.command_sent.set()
        if self.auto_complete and self.transport is not None:
            lifecycle_payload = {
                "command_id": correlation_id,
                "actor_id": payload["actor_id"],
            }
            self.transport.receive_runtime_event(
                "intent_accepted",
                lifecycle_payload,
            )
            self.transport.receive_runtime_event(
                "intent_started",
                lifecycle_payload,
            )
            self.transport.receive_runtime_event(
                "intent_terminal",
                {**lifecycle_payload, "status": "completed"},
            )
        return True

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        self.cancelled.append({"command_id": command_id, "actor_id": actor_id})
        return True


def make_body(body_id: str = "elfie-1") -> tuple[NativeBody, FakeGodotGateway]:
    gateway = FakeGodotGateway()
    transport = GodotTransport(gateway)
    gateway.transport = transport
    body = NativeBody(body_id=body_id, transport=transport)
    return body, gateway


def _command_fields(command_id: str) -> dict[str, object]:
    return {
        "command_id": CommandId(command_id),
        "turn_id": TurnId("turn-native"),
        "intent_id": IntentId(f"intent-{command_id}"),
        "body_id": BodyId("elfie-1"),
        "issued_at": NOW,
        "deadline": NOW + timedelta(seconds=1),
        "capability_revision": 1,
    }


def test_native_body_implements_typed_body_port() -> None:
    body, gateway = make_body()

    assert isinstance(body, BodyPort)
    assert body.describe().mode is BodyMode.NATIVE
    assert body.snapshot_body(now=NOW).connected is False
    assert gateway.sent == []


def test_native_body_does_not_consume_legacy_gateway_callbacks() -> None:
    body, gateway = make_body()
    body.connect()

    assert body.read_sensor_events() == []
    assert body.snapshot_body(now=NOW).pending_event_count == 0


def test_native_body_reuses_existing_speech_expression_and_movement_events() -> None:
    body, gateway = make_body()
    body.connect()

    speech = SpeechCommand(
        command_type="speech",
        text="你好",
        **_command_fields("speech-1"),
    )
    motion = MotionCommand(
        command_type="motion",
        kind="chat_look",
        target="chair_1",
        posture="sitting",
        **_command_fields("motion-1"),
    )
    expression = ExpressionCommand(
        command_type="expression",
        kind="happy",
        **_command_fields("expression-1"),
    )
    receipts = tuple(
        body.execute(command, now=NOW) for command in (speech, motion, expression)
    )

    assert all(batch[-1].status is CommandStatus.COMPLETED for batch in receipts)
    assert [message["action"] for message in gateway.sent] == [
        "execute_intent",
        "execute_intent",
        "execute_intent",
    ]
    assert gateway.sent[0]["payload"]["actor_id"] == "elfie-1"
    assert gateway.sent[0]["payload"]["text"] == "你好"
    assert gateway.sent[1]["payload"]["anchor_id"] == "chair_1"
    assert gateway.sent[2]["payload"]["expression"] == "happy"


def test_native_body_disconnects_without_changing_the_shared_gateway() -> None:
    body, gateway = make_body()
    body.connect()
    body.disconnect()

    result = body.execute(
        ExpressionCommand(
            command_type="expression",
            kind="blink_eyes",
            **_command_fields("disconnected-1"),
        ),
        now=NOW,
    )

    assert body.read_sensor_events() == []
    assert result[-1].status is CommandStatus.REJECTED
    assert gateway.sent == []


def test_native_body_reports_unsupported_emergency_stop() -> None:
    body, gateway = make_body()
    body.connect()
    result = body.execute(
        EmergencyStopCommand(
            command_type="emergency_stop",
            reason="danger",
            **_command_fields("emergency-1"),
        ),
        now=NOW,
    )

    assert result[-1].status is CommandStatus.COMPLETED
    assert result[-1].error is None
    assert gateway.sent == []


def test_native_body_rejects_malformed_wire_command() -> None:
    body, gateway = make_body()
    body.connect()

    result = body.execute_wire(
        {
            "command_id": "bad-command",
            "turn_id": "turn-native",
            "intent_id": "intent-bad",
            "body_id": "elfie-1",
            "capability_revision": 1,
            "command_type": "motion",
        },
        now=NOW,
    )

    assert result[-1].status is CommandStatus.REJECTED
    assert result[-1].error is not None
    assert result[-1].error.code == "bad_payload"
    assert gateway.sent == []


def test_shared_transport_keeps_body_handlers_without_gateway_callbacks() -> None:
    gateway = FakeGodotGateway()
    transport = GodotTransport(gateway)
    first = NativeBody(body_id="elfie-1", transport=transport)
    second = NativeBody(body_id="elfie-2", transport=transport)
    first.connect()
    second.connect()

    assert first.read_sensor_events() == []
    assert second.read_sensor_events() == []


def test_disconnected_native_body_rejects_without_reaching_godot() -> None:
    body, gateway = make_body()

    command = ExpressionCommand(
        command_type="expression",
        kind="blink_eyes",
        **_command_fields("disconnected-native"),
    )
    result = body.execute(command, now=NOW)

    assert body.snapshot_body(now=NOW).connected is False
    assert result[-1].command_id == command.command_id
    assert result[-1].status is CommandStatus.REJECTED
    assert gateway.sent == []


def test_runtime_terminal_preserves_command_identity() -> None:
    body, gateway = make_body()
    body.connect()
    command = MotionCommand(
        command_type="motion",
        kind="walking",
        target="activity-01/activity",
        **_command_fields("motion-wire-1"),
    )

    receipts = body.execute(command, now=NOW)

    assert all(receipt.command_id == command.command_id for receipt in receipts)


def test_native_body_waits_for_actual_runtime_terminal() -> None:
    body, gateway = make_body()
    body.connect()
    gateway.auto_complete = False
    command = MotionCommand(
        command_type="motion",
        kind="walking",
        target="activity-01/activity",
        **_command_fields("wait-for-runtime"),
    )
    result: list[tuple] = []
    worker = Thread(target=lambda: result.append(body.execute(command, now=NOW)))

    worker.start()
    assert gateway.command_sent.wait(timeout=0.5)
    lifecycle = {"command_id": "wait-for-runtime", "actor_id": "elfie-1"}
    body.transport.receive_runtime_event("intent_accepted", lifecycle)
    body.transport.receive_runtime_event("intent_started", lifecycle)
    assert worker.is_alive()
    body.transport.receive_runtime_event(
        "intent_terminal",
        {**lifecycle, "status": "completed"},
    )
    worker.join(timeout=0.5)

    assert not worker.is_alive()
    assert [receipt.status for receipt in result[0]] == [
        CommandStatus.ACCEPTED,
        CommandStatus.STARTED,
        CommandStatus.COMPLETED,
    ]


def test_native_body_timeout_sends_cancel_and_late_terminal_is_ignored() -> None:
    body, gateway = make_body()
    body.connect()
    gateway.auto_complete = False
    fields = _command_fields("runtime-timeout")
    fields["deadline"] = NOW + timedelta(milliseconds=20)
    command = MotionCommand(
        command_type="motion",
        kind="walking",
        target="activity-01/activity",
        **fields,
    )

    receipts = body.execute(command, now=NOW)
    body.transport.receive_runtime_event(
        "intent_terminal",
        {
            "command_id": "runtime-timeout",
            "actor_id": "elfie-1",
            "status": "completed",
        },
    )

    assert receipts[-1].status is CommandStatus.TIMED_OUT
    assert gateway.cancelled == [
        {"command_id": "runtime-timeout", "actor_id": "elfie-1"}
    ]


def test_runtime_generation_change_interrupts_pending_body_command() -> None:
    body, gateway = make_body()
    body.connect()
    gateway.auto_complete = False
    command = MotionCommand(
        command_type="motion",
        kind="walking",
        target="activity-01/activity",
        **_command_fields("runtime-interrupted"),
    )
    result: list[tuple] = []
    worker = Thread(target=lambda: result.append(body.execute(command, now=NOW)))

    worker.start()
    assert gateway.command_sent.wait(timeout=0.5)
    body.transport.interrupt_pending("runtime generation changed")
    worker.join(timeout=0.5)

    assert not worker.is_alive()
    assert result[0][-1].status is CommandStatus.INTERRUPTED


def test_cancel_all_wakes_pending_body_command() -> None:
    body, gateway = make_body()
    body.connect()
    gateway.auto_complete = False
    command = MotionCommand(
        command_type="motion",
        kind="walking",
        target="activity-01/activity",
        **_command_fields("runtime-cancel-all"),
    )
    result: list[tuple] = []
    worker = Thread(target=lambda: result.append(body.execute(command, now=NOW)))

    worker.start()
    assert gateway.command_sent.wait(timeout=0.5)
    body.transport.cancel_all(actor_id="elfie-1")
    worker.join(timeout=0.5)

    assert not worker.is_alive()
    assert result[0][-1].status is CommandStatus.INTERRUPTED
    assert gateway.cancelled == [
        {"command_id": "runtime-cancel-all", "actor_id": "elfie-1"}
    ]
