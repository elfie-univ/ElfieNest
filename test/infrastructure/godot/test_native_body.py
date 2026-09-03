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
    ObservationCommand,
    SpeechCommand,
)
from elfie.message_types import CommandId, IntentId, TurnId
from infrastructure.godot import GodotTransport, NativeBody
from infrastructure.godot.gateway.messages import (
    EventName,
    RuntimeEventFrame,
    SemanticLane,
)

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


class FakeGodotGateway:
    def __init__(self) -> None:
        self.sent: List[Dict[str, Any]] = []
        self.cancelled: List[Dict[str, str]] = []
        self.transport: GodotTransport | None = None
        self.auto_complete = True
        self.command_sent = Event()
        self.sinks: Dict[str, GodotTransport] = {}
        self.event_sequence = 0

    def send_body_command(
        self,
        payload: Dict[str, Any],
        *,
        cause_id: str,
    ) -> bool:
        self.sent.append({"action": "execute_intent", "payload": payload})
        self.command_sent.set()
        if self.auto_complete and self.transport is not None:
            lifecycle_payload = {
                "command_id": cause_id,
                "actor_id": payload["actor_id"],
                "intent_id": payload["intent_id"],
                "body_generation": payload["body_generation"],
            }
            self.transport.receive_runtime_event(
                self.runtime_event(EventName.INTENT_ACCEPTED, lifecycle_payload)
            )
            self.transport.receive_runtime_event(
                self.runtime_event(EventName.INTENT_STARTED, lifecycle_payload)
            )
            self.transport.receive_runtime_event(
                self.runtime_event(
                    EventName.INTENT_TERMINAL,
                    {**lifecycle_payload, "status": "completed"},
                )
            )
        return True

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        self.cancelled.append({"command_id": command_id, "actor_id": actor_id})
        return True

    def register_body_sink(self, actor_id: str, sink: GodotTransport) -> None:
        self.sinks[actor_id] = sink

    def unregister_body_sink(self, actor_id: str, sink: GodotTransport) -> None:
        if self.sinks.get(actor_id) is sink:
            self.sinks.pop(actor_id, None)

    def runtime_event(
        self,
        name: EventName,
        payload: Dict[str, Any],
    ) -> RuntimeEventFrame:
        self.event_sequence += 1
        command_id = payload.get("command_id")
        return RuntimeEventFrame(
            protocol=3,
            kind="event",
            lane=SemanticLane.BODY,
            name=name,
            message_id=f"runtime-event-{self.event_sequence}",
            cause_id=command_id if isinstance(command_id, str) else None,
            target_actor_id=str(payload["actor_id"]),
            runtime_id="runtime-main",
            generation=1,
            world_revision=1,
            occurred_at=NOW,
            payload=payload,
        )


def make_body(body_id: str = "elfie-1") -> tuple[NativeBody, FakeGodotGateway]:
    gateway = FakeGodotGateway()
    transport = GodotTransport(gateway, actor_id=body_id)
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
    assert gateway.sent[0]["payload"]["intent_id"] == "intent-speech-1"
    assert gateway.sent[0]["payload"]["body_generation"] == 1
    assert gateway.sent[0]["payload"]["initiator"] == "elfie"
    assert "text" not in gateway.sent[0]["payload"]
    assert gateway.sent[1]["payload"]["anchor_id"] == "chair_1"
    assert gateway.sent[2]["payload"]["expression"] == "happy"


def test_native_body_resolves_semantic_home_once_before_direct_motion() -> None:
    gateway = FakeGodotGateway()
    completed: list[str] = []
    resolved_payloads: list[dict[str, object]] = []
    transport = GodotTransport(
        gateway,
        actor_id="elfie-1",
        semantic_action=lambda payload: (
            resolved_payloads.append(dict(payload))
            or ("dorm-01/bed-01" if payload.get("anchor_id") == "home" else None)
        ),
        semantic_action_result=lambda _payload, result: completed.append(
            result.terminal_status
        ),
    )
    gateway.transport = transport
    body = NativeBody(body_id="elfie-1", transport=transport)
    body.connect()

    result = body.execute(
        MotionCommand(
            command_type="motion",
            kind="go_home",
            target="home",
            **_command_fields("home-1"),
        ),
        now=NOW,
    )

    assert result[-1].status is CommandStatus.COMPLETED
    assert gateway.sent[0]["payload"]["anchor_id"] == "dorm-01/bed-01"
    assert resolved_payloads[0]["intent_id"] == "intent-home-1"
    assert resolved_payloads[0]["body_generation"] == 1
    assert resolved_payloads[0]["initiator"] == "elfie"
    assert completed == ["completed"]


def test_native_body_requests_semantic_observation_through_godot_transport() -> None:
    gateway = FakeGodotGateway()
    requests: list[dict[str, object]] = []
    transport = GodotTransport(
        gateway,
        actor_id="elfie-1",
        visual_observation=lambda payload: requests.append(dict(payload)) or True,
    )
    gateway.transport = transport
    body = NativeBody(body_id="elfie-1", transport=transport)
    body.connect()

    receipts = body.execute(
        ObservationCommand(
            command_type="observation",
            observation_id="observation-1",
            max_results=8,
            **_command_fields("observation-1"),
        ),
        now=NOW,
    )

    assert [receipt.status for receipt in receipts] == [
        CommandStatus.ACCEPTED,
        CommandStatus.STARTED,
        CommandStatus.COMPLETED,
    ]
    assert requests == [
        {
            "command_id": "observation-1",
            "intent": "observe",
            "observation_id": "observation-1",
            "max_results": 8,
            "actor_id": "elfie-1",
            "intent_id": "intent-observation-1",
            "body_generation": 1,
            "initiator": "elfie",
        }
    ]
    assert gateway.sent == []


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


def test_shared_gateway_keeps_actor_scoped_body_transports() -> None:
    gateway = FakeGodotGateway()
    first = NativeBody(
        body_id="elfie-1",
        transport=GodotTransport(gateway, actor_id="elfie-1"),
    )
    second = NativeBody(
        body_id="elfie-2",
        transport=GodotTransport(gateway, actor_id="elfie-2"),
    )
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


def test_runtime_receipts_preserve_source_event_cause_and_time() -> None:
    body, _gateway = make_body()
    body.connect()
    command = MotionCommand(
        command_type="motion",
        kind="walking",
        target="activity-01/activity",
        **_command_fields("motion-source-identity"),
    )

    receipts = body.execute(command, now=NOW)

    assert [str(receipt.receipt_id) for receipt in receipts] == [
        "runtime-event-1",
        "runtime-event-2",
        "runtime-event-3",
    ]
    assert {str(receipt.cause_id) for receipt in receipts} == {"motion-source-identity"}
    assert {receipt.occurred_at for receipt in receipts} == {NOW}


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
    lifecycle = {
        "command_id": "wait-for-runtime",
        "actor_id": "elfie-1",
        "intent_id": "intent-wait-for-runtime",
        "body_generation": 1,
    }
    body.transport.receive_runtime_event(
        gateway.runtime_event(EventName.INTENT_ACCEPTED, lifecycle)
    )
    body.transport.receive_runtime_event(
        gateway.runtime_event(EventName.INTENT_STARTED, lifecycle)
    )
    assert worker.is_alive()
    body.transport.receive_runtime_event(
        gateway.runtime_event(
            EventName.INTENT_TERMINAL,
            {**lifecycle, "status": "completed"},
        )
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
        gateway.runtime_event(
            EventName.INTENT_TERMINAL,
            {
                "command_id": "runtime-timeout",
                "actor_id": "elfie-1",
                "intent_id": "intent-runtime-timeout",
                "body_generation": 1,
                "status": "completed",
            },
        )
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
