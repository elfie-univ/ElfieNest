from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List

from elfie.body import (
    BodyId,
    BodyMode,
    BodyPort,
    CommandStatus,
    EmergencyStopCommand,
    ExpressionCommand,
    GodotTransport,
    MotionCommand,
    NativeBody,
    ProprioceptionSample,
    SpeechCommand,
)
from elfie.message_types import ActorId, CommandId, EventId, IntentId, TurnId

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


class FakeGodotGateway:
    def __init__(self) -> None:
        self.callbacks: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.sent: List[Dict[str, Any]] = []
        self.runtime_ready = False

    def register_callback(
        self, event_name: str, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        self.callbacks.setdefault(event_name, []).append(callback)

    def send_action(self, action: str, payload: Dict[str, Any]) -> None:
        self.sent.append({"action": action, "payload": payload})

    def emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        for callback in self.callbacks.get(event_name, []):
            callback(payload)


def make_body(body_id: str = "elfie-1") -> tuple[NativeBody, FakeGodotGateway]:
    gateway = FakeGodotGateway()
    body = NativeBody(body_id=body_id, transport=GodotTransport(gateway))
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
    assert gateway.callbacks == {}


def test_native_body_receives_only_physical_events_for_its_identity() -> None:
    body, gateway = make_body()
    body.connect()

    gateway.emit("user_message", {"elfie_id": "other", "message": "忽略"})
    gateway.emit(
        "user_message",
        {"elfie_id": "elfie-1", "message": "你好", "message_id": "msg-1"},
    )
    gateway.emit(
        "arrived_at",
        {"elfie_id": "elfie-1", "target": "chair_1", "posture": "sitting"},
    )

    events = body.read_sensor_events()

    assert [event.payload.kind for event in events] == ["proprioception_sample"]
    assert isinstance(events[0].payload, ProprioceptionSample)
    assert events[0].payload.target == "chair_1"
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
        body.execute(command, now=NOW)
        for command in (speech, motion, expression)
    )

    assert all(batch[-1].status is CommandStatus.COMPLETED for batch in receipts)
    assert [message["action"] for message in gateway.sent] == [
        "speak_event",
        "go_to",
        "emotion_expression",
    ]
    assert gateway.sent[0]["payload"]["elfie_id"] == "elfie-1"
    assert gateway.sent[0]["payload"]["text"] == "你好"
    assert gateway.sent[1]["payload"]["target"] == "chair_1"
    assert gateway.sent[2]["payload"]["expression"] == "happy"


def test_native_body_disconnects_without_changing_the_shared_gateway() -> None:
    body, gateway = make_body()
    body.connect()
    body.disconnect()

    gateway.emit("arrived_at", {"elfie_id": "elfie-1", "target": "chair_1"})
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
    gateway.runtime_ready = True

    result = body.execute(
        EmergencyStopCommand(
            command_type="emergency_stop",
            reason="danger",
            **_command_fields("emergency-1"),
        ),
        now=NOW,
    )

    assert result[-1].status is CommandStatus.REJECTED
    assert result[-1].error is not None
    assert result[-1].error.code == "unsupported_capability"
    assert body.transport.runtime_ready is True
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


def test_shared_transport_registers_gateway_callbacks_only_once() -> None:
    gateway = FakeGodotGateway()
    transport = GodotTransport(gateway)
    first = NativeBody(body_id="elfie-1", transport=transport)
    second = NativeBody(body_id="elfie-2", transport=transport)
    first.connect()
    second.connect()

    assert all(len(callbacks) == 1 for callbacks in gateway.callbacks.values())

    gateway.emit("arrived_at", {"elfie_id": "elfie-2", "target": "chair_1"})

    assert first.read_sensor_events() == []
    second_event = second.read_sensor_events()[0]
    assert isinstance(second_event.payload, ProprioceptionSample)
    assert second_event.payload.target == "chair_1"


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


def test_native_sensor_edge_preserves_wire_identity() -> None:
    body, gateway = make_body()
    body.connect()
    gateway.emit(
        "arrived_at",
        {
            "elfie_id": "elfie-1",
            "message_id": "utterance-1",
            "actor_id": "owner-1",
            "target": "chair_1",
            "posture": "sitting",
        },
    )

    event = body.read_sensor_events()[0]

    assert event.event_id == EventId("utterance-1")
    assert event.body_id == BodyId("elfie-1")
    assert event.source.actor_id == ActorId("owner-1")
    assert isinstance(event.payload, ProprioceptionSample)
