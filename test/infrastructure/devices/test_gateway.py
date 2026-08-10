"""Device gateway bridges the typed BodyPort contract to LAN machine frames."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from elfie.body import (
    BodyCapabilities,
    BodyId,
    BodySensorEvent,
    CommandStatus,
    ExternalBody,
    SpeechCommand,
    UtteranceFinal,
)
from elfie.message_types import ActorId, ActorRef, CommandId, EventId, IntentId, TurnId
from infrastructure.devices import DeviceGateway, DeviceGatewayTransport

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def _sensor_event() -> BodySensorEvent:
    return BodySensorEvent(
        event_id=EventId("gateway-sensor-1"),
        body_id=BodyId("living-room-toy"),
        source=ActorRef(actor_id=ActorId("device-owner"), source_kind="microphone"),
        occurred_at=NOW,
        received_at=NOW,
        payload=UtteranceFinal(kind="utterance_final", text="你好，小精灵"),
    )


def _speech_command() -> SpeechCommand:
    return SpeechCommand(
        command_type="speech",
        command_id=CommandId("gateway-command-1"),
        turn_id=TurnId("gateway-turn-1"),
        intent_id=IntentId("gateway-intent-1"),
        body_id=BodyId("living-room-toy"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=10),
        capability_revision=1,
        text="你好，我在这里。",
    )


def test_gateway_transport_delivers_device_sensor_events_and_queues_actions() -> None:
    gateway = DeviceGateway()
    gateway.connect_device("dev_living_room")
    transport = DeviceGatewayTransport(gateway, "dev_living_room")
    body = ExternalBody(
        body_id="living-room-toy",
        display_name="客厅玩具",
        capabilities=BodyCapabilities(
            sensors=frozenset({"utterance_final"}),
            actions=frozenset({"speech.say"}),
        ),
        transport=transport,
    )
    body.connect()

    delivered = gateway.deliver_sensor_event("dev_living_room", _sensor_event())
    receipts = body.execute(_speech_command(), now=NOW)

    assert delivered is True
    assert body.read_sensor_events() == [_sensor_event()]
    assert receipts[-1].status is CommandStatus.ACCEPTED
    assert gateway.drain_commands("dev_living_room") == [_speech_command()]


def test_gateway_transport_disconnects_from_the_device_sensor_stream() -> None:
    gateway = DeviceGateway()
    transport = DeviceGatewayTransport(gateway, "dev_living_room")
    received: list[BodySensorEvent] = []
    transport.connect(received.append)
    transport.disconnect()

    delivered = gateway.deliver_sensor_event("dev_living_room", _sensor_event())

    assert delivered is False
    assert received == []
