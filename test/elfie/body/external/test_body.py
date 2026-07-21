from datetime import datetime, timezone
from typing import Any, Mapping

from elfie.body import (
    BodyCapabilities,
    BodyCommand,
    BodyEvent,
    BodyId,
    BodyMode,
    BodyPort,
    BodySensorEvent,
    CommandResult,
    CommandStatus,
    ExternalBody,
    UtteranceFinal,
)
from elfie.message_types import ActorId, ActorRef, EventId


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

    def send_command(self, command: BodyCommand) -> CommandResult:
        self.commands.append(command)
        if self.invalid_result:
            return CommandResult(
                command_id="wrong-command",
                action="wrong-action",
                status=CommandStatus.COMPLETED,
            )
        return CommandResult(
            command_id=command.command_id,
            action=command.action,
            status=CommandStatus.COMPLETED,
            output={"robot_ack": True},
        )

    def snapshot(self) -> Mapping[str, Any]:
        return {"connected": self.connected}

    def emit(self, event: BodyEvent | BodySensorEvent) -> None:
        assert self.handler is not None
        self.handler(event)


def make_external_body() -> tuple[ExternalBody, FakeExternalTransport]:
    transport = FakeExternalTransport()
    body = ExternalBody(
        body_id="robot-1",
        display_name="桌面机器人",
        capabilities=BodyCapabilities(
            sensors=frozenset({"hearing", "vision"}),
            actions=frozenset({"speech.say", "system.emergency_stop"}),
        ),
        transport=transport,
    )
    return body, transport


def test_external_body_implements_port_and_declares_external_mode() -> None:
    body, _transport = make_external_body()

    assert isinstance(body, BodyPort)
    assert body.describe().mode is BodyMode.EXTERNAL
    assert body.describe().display_name == "桌面机器人"


def test_external_body_filters_events_by_declared_sensor_capabilities() -> None:
    body, transport = make_external_body()
    body.connect()
    transport.emit(
        BodyEvent(sensor="hearing", payload={"text": "你好"}, source="microphone")
    )
    transport.emit(
        BodyEvent(sensor="temperature", payload={"value": 30}, source="sensor")
    )

    events = body.read_events()

    assert len(events) == 1
    assert events[0].sensor == "hearing"


def test_external_body_validates_and_forwards_supported_actions() -> None:
    body, transport = make_external_body()
    body.connect()

    accepted = body.execute(BodyCommand(action="speech.say", parameters={"text": "你好"}))
    rejected = body.execute(BodyCommand(action="tail.wag"))

    assert accepted.status is CommandStatus.COMPLETED
    assert accepted.output["robot_ack"] is True
    assert rejected.status is CommandStatus.REJECTED
    assert [command.action for command in transport.commands] == ["speech.say"]


def test_external_body_exposes_transport_snapshot_and_emergency_stop() -> None:
    body, transport = make_external_body()
    body.connect()

    result = body.emergency_stop()
    snapshot = body.snapshot()

    assert result.status is CommandStatus.COMPLETED
    assert transport.commands[-1].action == "system.emergency_stop"
    assert snapshot.metadata["transport_id"] == "robot-plugin"
    assert snapshot.metadata["transport"]["connected"] is True


def test_external_body_rejects_acknowledgement_for_a_different_command() -> None:
    body, transport = make_external_body()
    body.connect()
    transport.invalid_result = True

    result = body.execute(BodyCommand(action="speech.say"))

    assert result.status is CommandStatus.FAILED
    assert "与原命令不匹配" in result.error


def test_legacy_external_port_characterization_before_contract_migration() -> None:
    """Given a disconnected external body, rejection never reaches transport."""
    body, transport = make_external_body()

    result = body.execute(
        BodyCommand(action="speech.say", command_id="legacy-command")
    )

    assert body.describe().body_id == "robot-1"
    assert body.snapshot().connected is False
    assert result.command_id == "legacy-command"
    assert result.status is CommandStatus.REJECTED
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
        occurred_at=datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc),
        received_at=datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc),
        payload=UtteranceFinal(kind="utterance_final", text="你好"),
    )
    body.connect()
    transport.emit(event)

    received = body.read_sensor_events()

    assert received == [event]
