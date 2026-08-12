from __future__ import annotations

from datetime import datetime, timedelta, timezone

from elfie.body import (
    BodyCapabilities,
    BodyCommand,
    BodyId,
    BodyMode,
    BodyPort,
    BodySensorEvent,
    CommandReceipt,
    CommandStatus,
    EmergencyStopCommand,
    MotionCommand,
    SpeechCommand,
    UtteranceFinal,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    CommandId,
    EventId,
    IntentId,
    TurnId,
)
from infrastructure.devices import ExternalBody

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


class FakeExternalTransport:
    transport_id = "robot-plugin"

    def __init__(self) -> None:
        self.handler = None
        self.connected = False
        self.commands = []
        self.invalid_result = False

    def connect(self, event_handler) -> None:
        self.handler = event_handler
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def send_command(
        self,
        command: BodyCommand,
    ) -> CommandReceipt:
        self.commands.append(command)
        if self.invalid_result:
            return CommandReceipt.completed(command, occurred_at=NOW).model_copy(
                update={"command_id": CommandId("wrong-command")}
            )
        return CommandReceipt.completed(command, occurred_at=NOW)

    def emit(self, event: BodySensorEvent) -> None:
        assert self.handler is not None
        self.handler(event)


def make_external_body() -> tuple[ExternalBody, FakeExternalTransport]:
    transport = FakeExternalTransport()
    body = ExternalBody(
        body_id="robot-1",
        display_name="桌面机器人",
        capabilities=BodyCapabilities(
            sensors=frozenset({"utterance_final", "vision_sample"}),
            actions=frozenset({"speech.say", "system.emergency_stop"}),
        ),
        transport=transport,
    )
    return body, transport


def make_speech_command(
    *, command_id: str = "speech-command", body_id: str = "robot-1"
) -> SpeechCommand:
    return SpeechCommand(
        command_type="speech",
        command_id=CommandId(command_id),
        turn_id=TurnId("turn-external"),
        intent_id=IntentId(f"intent-{command_id}"),
        body_id=BodyId(body_id),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=1,
        text="你好",
    )


def make_emergency_command() -> EmergencyStopCommand:
    return EmergencyStopCommand(
        command_type="emergency_stop",
        command_id=CommandId("emergency-command"),
        turn_id=TurnId("turn-external"),
        intent_id=IntentId("intent-emergency"),
        body_id=BodyId("robot-1"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=1,
        reason="danger",
    )


def test_external_body_implements_port_and_declares_external_mode() -> None:
    body, _transport = make_external_body()

    assert isinstance(body, BodyPort)
    assert body.describe().mode is BodyMode.EXTERNAL
    assert body.describe().display_name == "桌面机器人"


def test_external_body_filters_events_by_declared_sensor_capabilities() -> None:
    body, transport = make_external_body()
    body.connect()
    accepted = BodySensorEvent(
        event_id=EventId("utterance-accepted"),
        body_id=BodyId("robot-1"),
        source=ActorRef(actor_id=ActorId("owner-1"), source_kind="microphone"),
        occurred_at=NOW,
        received_at=NOW,
        payload=UtteranceFinal(kind="utterance_final", text="你好"),
    )
    transport.emit(accepted)

    events = body.read_sensor_events()

    assert events == [accepted]


def test_external_body_validates_and_forwards_supported_actions() -> None:
    body, transport = make_external_body()
    body.connect()

    accepted = body.execute(make_speech_command(), now=NOW)
    rejected = body.execute(
        MotionCommand(
            command_type="motion",
            command_id=CommandId("tail-command"),
            turn_id=TurnId("turn-external"),
            intent_id=IntentId("intent-tail"),
            body_id=BodyId("robot-1"),
            issued_at=NOW,
            deadline=NOW + timedelta(seconds=1),
            capability_revision=1,
            kind="tail.wag",
        ),
        now=NOW,
    )

    assert accepted[-1].status is CommandStatus.COMPLETED
    assert rejected[-1].status is CommandStatus.REJECTED
    assert [command.command_type for command in transport.commands] == ["speech"]


def test_external_body_executes_emergency_stop_and_reports_snapshot() -> None:
    body, transport = make_external_body()
    body.connect()

    command = make_emergency_command()
    result = body.execute(command, now=NOW)
    snapshot = body.snapshot_body(now=NOW)

    assert result[-1].status is CommandStatus.COMPLETED
    assert transport.commands[-1] is command
    assert snapshot.connected is True
    assert snapshot.last_command_id == command.command_id


def test_external_body_rejects_acknowledgement_for_a_different_command() -> None:
    body, transport = make_external_body()
    body.connect()
    transport.invalid_result = True

    result = body.execute(make_speech_command(), now=NOW)

    assert result[-1].status is CommandStatus.REJECTED
    assert result[-1].error is not None
    assert result[-1].error.code == "receipt_correlation_mismatch"


def test_disconnected_external_body_rejects_without_reaching_transport() -> None:
    body, transport = make_external_body()

    command = make_speech_command(command_id="disconnected-command")
    result = body.execute(command, now=NOW)

    assert body.describe().body_id == "robot-1"
    assert body.snapshot_body(now=NOW).connected is False
    assert result[-1].command_id == command.command_id
    assert result[-1].status is CommandStatus.REJECTED
    assert transport.commands == []


def test_external_sensor_edge_preserves_typed_event_identity() -> None:
    transport = FakeExternalTransport()
    body = ExternalBody(
        body_id="robot-1",
        display_name="Typed robot",
        capabilities=BodyCapabilities(sensors=frozenset({"utterance_final"})),
        transport=transport,
    )
    event = BodySensorEvent(
        event_id=EventId("utterance-1"),
        body_id=BodyId("robot-1"),
        source=ActorRef(actor_id=ActorId("owner-1"), source_kind="microphone"),
        occurred_at=NOW,
        received_at=NOW,
        payload=UtteranceFinal(kind="utterance_final", text="你好"),
    )
    body.connect()
    transport.emit(event)

    received = body.read_sensor_events()

    assert received == [event]
