from __future__ import annotations

from datetime import datetime, timezone

import pytest

from elfie.body.contracts import TactileImpact
from infrastructure.godot.body_transport import GodotTransport
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import (
    EventName,
    RuntimeEventFrame,
    SemanticLane,
)
from infrastructure.godot.gateway.session import StaleRuntimeEventError
from infrastructure.godot.native_body import NativeBody

OCCURRED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[RuntimeEventFrame] = []

    def receive_runtime_event(self, event: RuntimeEventFrame) -> None:
        self.events.append(event)


def _event(
    *,
    name: EventName,
    lane: SemanticLane,
    message_id: str,
    target_actor_id: str | None,
    payload: dict[str, object],
    cause_id: str | None = None,
    generation: int = 1,
) -> RuntimeEventFrame:
    return RuntimeEventFrame(
        protocol=3,
        kind="event",
        lane=lane,
        name=name,
        message_id=message_id,
        cause_id=cause_id,
        target_actor_id=target_actor_id,
        runtime_id="runtime-main",
        generation=generation,
        world_revision=4,
        occurred_at=OCCURRED_AT,
        payload=payload,
    )


def test_gateway_delivers_tactile_input_only_to_target_body() -> None:
    gateway = GodotAPIServer(port=0, handshake_nonce="nonce")
    connection = gateway.runtime_session.acquire_authority("runtime-main")
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

    gateway.route_runtime_event(
        _event(
            name=EventName.TACTILE_CONTACT,
            lane=SemanticLane.BODY,
            message_id="touch-1",
            cause_id="move-1",
            target_actor_id="elfie-1",
            generation=connection.generation,
            payload={
                "actor_id": "elfie-1",
                "intensity": 0.4,
                "direction": "left",
                "contact_kind": "world",
                "source_semantic_id": "wall-1",
            },
        )
    )

    (sensor_event,) = first.read_sensor_events()
    assert sensor_event.event_id == "touch-1"
    assert sensor_event.cause_id == "move-1"
    assert sensor_event.occurred_at == OCCURRED_AT
    assert isinstance(sensor_event.payload, TactileImpact)
    assert sensor_event.payload.force_newtons is None
    assert second.read_sensor_events() == []
    assert gateway.drain_runtime_events() == ()


def test_gateway_keeps_speech_reach_on_nest_lane_without_body_delivery() -> None:
    gateway = GodotAPIServer(port=0, handshake_nonce="nonce")
    connection = gateway.runtime_session.acquire_authority("runtime-main")
    body = NativeBody(
        body_id="elfie-1",
        transport=GodotTransport(gateway, actor_id="elfie-1"),
    )
    body.connect()

    gateway.route_runtime_event(
        _event(
            name=EventName.SPEECH_REACH,
            lane=SemanticLane.NEST,
            message_id="speech-reach-1",
            cause_id="speech-command-1",
            target_actor_id=None,
            generation=connection.generation,
            payload={
                "command_id": "speech-command-1",
                "actor_id": "elfie-1",
                "zone_id": "common-1",
                "audience_actor_ids": ["elfie-2"],
            },
        )
    )

    assert body.read_sensor_events() == []
    assert [event.message_id for event in gateway.drain_runtime_events()] == [
        "speech-reach-1"
    ]


def test_gateway_routes_receipt_once_to_target_and_rejects_stale_generation() -> None:
    gateway = GodotAPIServer(port=0, handshake_nonce="nonce")
    connection = gateway.runtime_session.acquire_authority("runtime-main")
    first = RecordingSink()
    second = RecordingSink()
    gateway.register_body_sink("elfie-1", first)
    gateway.register_body_sink("elfie-2", second)
    receipt = _event(
        name=EventName.INTENT_STARTED,
        lane=SemanticLane.BODY,
        message_id="receipt-1",
        cause_id="command-1",
        target_actor_id="elfie-1",
        generation=connection.generation,
        payload={
            "command_id": "command-1",
            "intent_id": "intent-1",
            "actor_id": "elfie-1",
            "body_generation": 1,
        },
    )

    gateway.route_runtime_event(receipt)
    gateway.route_runtime_event(receipt)

    assert first.events == [receipt]
    assert second.events == []
    assert gateway.drain_runtime_events() == ()
    with pytest.raises(StaleRuntimeEventError):
        gateway.route_runtime_event(
            receipt.model_copy(update={"generation": connection.generation + 1})
        )


def test_runtime_connection_readiness_is_separate_from_world_configuration() -> None:
    gateway = GodotAPIServer(port=0, handshake_nonce="nonce")
    connection = gateway.runtime_session.acquire_authority("runtime-main")

    assert gateway.runtime_ready is True
    assert gateway.runtime_world_revision is None

    gateway.mark_world_configured(connection, world_revision=4)

    assert gateway.runtime_ready is True
    assert gateway.runtime_world_revision == 4
