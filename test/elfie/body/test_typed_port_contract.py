"""Shared contract behavior for every Body implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest

from elfie.body import (
    BodyCapabilities,
    BodyPort,
    HeadlessBody,
)
from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    CommandReceipt,
    CommandStatus,
    MotionCommand,
    SpeechCommand,
    UtteranceFinal,
)
from elfie.message_types import ActorId, ActorRef, CommandId, EventId, IntentId, TurnId
from infrastructure.devices import ExternalBody
from infrastructure.godot import GodotTransport, NativeBody
from infrastructure.godot.gateway.messages import (
    EventName,
    RuntimeEventFrame,
    SemanticLane,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


class RecordingGodotGateway:
    def __init__(self) -> None:
        self.sent = []
        self.transport = None

    def send_body_command(self, payload, *, cause_id) -> bool:
        self.sent.append(payload)
        lifecycle = {
            "command_id": cause_id,
            "actor_id": payload["actor_id"],
            "intent_id": payload["intent_id"],
            "body_generation": payload["body_generation"],
        }
        self.transport.receive_runtime_event(
            self._event(EventName.INTENT_ACCEPTED, lifecycle, 1)
        )
        self.transport.receive_runtime_event(
            self._event(EventName.INTENT_STARTED, lifecycle, 2)
        )
        self.transport.receive_runtime_event(
            self._event(
                EventName.INTENT_TERMINAL,
                {**lifecycle, "status": "completed"},
                3,
            )
        )
        return True

    def cancel_body_command(self, *, command_id, actor_id) -> bool:
        return True

    def register_body_sink(self, actor_id, sink) -> None:
        _ = actor_id, sink

    def unregister_body_sink(self, actor_id, sink) -> None:
        _ = actor_id, sink

    @staticmethod
    def _event(name, payload, sequence) -> RuntimeEventFrame:
        return RuntimeEventFrame(
            protocol=3,
            kind="event",
            lane=SemanticLane.BODY,
            name=name,
            message_id=f"event-{sequence}",
            cause_id=payload["command_id"],
            target_actor_id=payload["actor_id"],
            runtime_id="runtime-main",
            generation=1,
            world_revision=1,
            occurred_at=NOW,
            payload=payload,
        )


class RecordingExternalTransport:
    transport_id = "typed-test-transport"

    def __init__(self) -> None:
        self.handler = None
        self.commands = []
        self.connected = False

    def connect(self, event_handler) -> None:
        self.handler = event_handler
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def send_command(self, command) -> CommandReceipt:
        self.commands.append(command)
        return CommandReceipt.completed(command, occurred_at=NOW)

    def snapshot(self):
        return {"connected": self.connected}


def make_headless() -> HeadlessBody:
    return HeadlessBody(body_id="body-1")


def make_native() -> NativeBody:
    gateway = RecordingGodotGateway()
    transport = GodotTransport(gateway, actor_id="body-1")
    gateway.transport = transport
    return NativeBody(body_id="body-1", transport=transport)


def make_external() -> ExternalBody:
    transport = RecordingExternalTransport()
    return ExternalBody(
        body_id="body-1",
        display_name="Typed external body",
        capabilities=BodyCapabilities(
            sensors=frozenset({"utterance_final"}),
            actions=frozenset({"speech.say", "gesture.wave"}),
            revision=1,
        ),
        transport=transport,
    )


@pytest.mark.parametrize("body_factory", [make_headless, make_native, make_external])
def test_each_body_emits_correlated_lifecycle_receipts(
    body_factory: Callable[[], HeadlessBody | NativeBody | ExternalBody],
) -> None:
    body = body_factory()
    body.connect()
    command = MotionCommand(
        command_type="motion",
        command_id=CommandId("command-1"),
        turn_id=TurnId("turn-1"),
        intent_id=IntentId("intent-1"),
        body_id=BodyId("body-1"),
        issued_at=NOW,
        deadline=NOW + timedelta(days=1),
        capability_revision=1,
        kind="gesture.wave",
    )

    receipts = body.execute(command, now=NOW)
    snapshot = body.snapshot_body(now=NOW)

    assert isinstance(body, BodyPort)
    assert snapshot.body_id == BodyId("body-1")
    assert snapshot.last_command_id == command.command_id
    assert [receipt.status for receipt in receipts] == [
        CommandStatus.ACCEPTED,
        CommandStatus.STARTED,
        CommandStatus.COMPLETED,
    ]
    assert all(receipt.command_id == command.command_id for receipt in receipts)
    assert all(receipt.turn_id == command.turn_id for receipt in receipts)
    assert all(receipt.intent_id == command.intent_id for receipt in receipts)


def test_expired_command_is_rejected_before_execution() -> None:
    body = HeadlessBody(body_id="body-1")
    body.connect()
    command = SpeechCommand(
        command_type="speech",
        command_id=CommandId("expired-command"),
        turn_id=TurnId("turn-1"),
        intent_id=IntentId("intent-1"),
        body_id=BodyId("body-1"),
        issued_at=NOW - timedelta(seconds=2),
        deadline=NOW - timedelta(seconds=1),
        capability_revision=1,
        text="too late",
    )

    receipts = body.execute(command, now=NOW)

    assert [receipt.status for receipt in receipts] == [CommandStatus.REJECTED]
    assert receipts[0].error is not None
    assert receipts[0].error.code == "deadline_expired"


def test_stale_capability_revision_is_rejected() -> None:
    body = HeadlessBody(
        body_id="body-1",
        capabilities=BodyCapabilities(actions=frozenset({"speech.say"}), revision=2),
    )
    body.connect()
    command = SpeechCommand(
        command_type="speech",
        command_id=CommandId("stale-command"),
        turn_id=TurnId("turn-1"),
        intent_id=IntentId("intent-1"),
        body_id=BodyId("body-1"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=1,
        text="hello",
    )

    receipts = body.execute(command, now=NOW)

    assert receipts[-1].status is CommandStatus.REJECTED
    assert receipts[-1].error is not None
    assert receipts[-1].error.code == "stale_capability_revision"


def test_external_rejects_unsupported_motion_without_transport_call() -> None:
    transport = RecordingExternalTransport()
    body = ExternalBody(
        body_id="body-1",
        display_name="No flight body",
        capabilities=BodyCapabilities(actions=frozenset({"speech.say"}), revision=1),
        transport=transport,
    )
    body.connect()
    command = MotionCommand(
        command_type="motion",
        command_id=CommandId("fly-command"),
        turn_id=TurnId("turn-1"),
        intent_id=IntentId("intent-1"),
        body_id=BodyId("body-1"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=1,
        kind="fly",
    )

    receipts = body.execute(command, now=NOW)

    assert receipts[-1].status is CommandStatus.REJECTED
    assert receipts[-1].error is not None
    assert receipts[-1].error.code == "unsupported_capability"
    assert transport.commands == []


def test_malformed_wire_command_returns_typed_rejection() -> None:
    body = HeadlessBody(body_id="body-1")

    receipts = body.execute_wire(
        {
            "command_type": "speech",
            "command_id": "bad-command",
            "turn_id": "turn-1",
            "intent_id": "intent-1",
            "body_id": "body-1",
            "issued_at": NOW,
            "deadline": NOW + timedelta(seconds=1),
            "capability_revision": 1,
        },
        now=NOW,
    )

    assert receipts[-1].status is CommandStatus.REJECTED
    assert receipts[-1].error is not None
    assert receipts[-1].error.code == "bad_payload"


def test_fully_malformed_wire_command_still_returns_typed_rejection() -> None:
    body = HeadlessBody(body_id="body-1")

    receipts = body.execute_wire({"command_type": "speech"}, now=NOW)

    assert receipts[0].status is CommandStatus.REJECTED
    assert receipts[0].command_id == CommandId("invalid-command")
    assert receipts[0].error is not None
    assert receipts[0].error.code == "bad_payload"


def test_headless_sensor_edge_preserves_event_identity() -> None:
    body = HeadlessBody(body_id="body-1")
    event = BodySensorEvent(
        event_id=EventId("utterance-1"),
        body_id=BodyId("body-1"),
        source=ActorRef(
            actor_id=ActorId("owner-1"),
            source_kind="microphone",
        ),
        occurred_at=NOW,
        received_at=NOW,
        payload=UtteranceFinal(kind="utterance_final", text="你好"),
    )
    body.inject_event(event)

    received = body.read_sensor_events()

    assert received == [event]
