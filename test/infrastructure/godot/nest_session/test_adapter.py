from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.orchestration.nest_session import RuntimeActor, RuntimeConnection
from app.orchestration.nest_session.models import (
    SceneManifest,
    WorldEventName,
    WorldSnapshot,
)
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from nest.godot_gateway.api import GodotAPIServer
from nest.godot_gateway.messages import CommandName, EventName, RuntimeEventFrame
from nest.godot_gateway.session import RuntimeConnection as GatewayConnection


def test_adapter_translates_world_operations_to_protocol_commands() -> None:
    gateway = MagicMock(spec=GodotAPIServer)
    gateway.runtime_connection = GatewayConnection("runtime-a", 2)
    gateway.send_runtime_command.side_effect = ("configure-1", "sync-1")
    adapter = GodotNestSessionAdapter(gateway=gateway)

    assert adapter.runtime_connection == RuntimeConnection("runtime-a", 2)
    assert (
        adapter.configure_world(
            nest_id="local-nest",
            bed_count=4,
            world_revision=1,
        )
        == "configure-1"
    )
    assert (
        adapter.synchronize_actors(
            (
                RuntimeActor(
                    actor_id="elfie-1",
                    species="fox",
                    appearance={},
                    home_anchor_id="dorm-01/bed-01",
                ),
            ),
            world_revision=1,
        )
        == "sync-1"
    )

    assert gateway.send_runtime_command.call_args_list[0].args == (
        CommandName.CONFIGURE_WORLD,
        {"nest_id": "local-nest", "bed_count": 4, "world_revision": 1},
    )
    assert (
        gateway.send_runtime_command.call_args_list[1].args[0]
        is CommandName.SYNC_ACTORS
    )


def test_adapter_maps_validated_manifest_without_exposing_protocol_frame() -> None:
    gateway = MagicMock(spec=GodotAPIServer)
    gateway.drain_runtime_events.return_value = (
        RuntimeEventFrame(
            protocol=2,
            kind="event",
            name=EventName.SCENE_MANIFEST,
            message_id="manifest-1",
            runtime_id="runtime-a",
            generation=1,
            world_revision=1,
            occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            payload={
                "nest_id": "local-nest",
                "world_revision": 1,
                "bed_count": 4,
                "capabilities": [],
                "zones": [
                    {
                        "zone_id": "dorm-01",
                        "kind": "dorm",
                        "label": "Dorm",
                        "stable_order": 0,
                        "active": True,
                    }
                ],
                "anchors": [
                    {
                        "anchor_id": "dorm-01/bed-01",
                        "zone_id": "dorm-01",
                        "kind": "bed",
                        "label": "Bed 1",
                        "stable_order": 0,
                        "active": True,
                    }
                ],
            },
        ),
    )
    adapter = GodotNestSessionAdapter(gateway=gateway)

    (event,) = adapter.drain_events()

    assert event.name is WorldEventName.SCENE_MANIFEST
    assert isinstance(event.payload, SceneManifest)
    assert event.payload.catalog.nest_id == "local-nest"
    assert event.payload.catalog.zones[0].anchors[0].anchor_id == "dorm-01/bed-01"


def test_adapter_maps_snapshot_to_semantic_resident_mirrors() -> None:
    gateway = MagicMock(spec=GodotAPIServer)
    gateway.drain_runtime_events.return_value = (
        RuntimeEventFrame(
            protocol=2,
            kind="event",
            name=EventName.WORLD_SNAPSHOT,
            message_id="snapshot-1",
            runtime_id="runtime-a",
            generation=1,
            world_revision=3,
            occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            payload={
                "world_revision": 3,
                "actors": [
                    {
                        "actor_id": "elfie-1",
                        "zone_id": "dorm-01",
                        "posture": "standing",
                        "active_command_id": None,
                    }
                ],
            },
        ),
    )
    adapter = GodotNestSessionAdapter(gateway=gateway)

    (event,) = adapter.drain_events()

    assert event.name is WorldEventName.WORLD_SNAPSHOT
    assert isinstance(event.payload, WorldSnapshot)
    assert event.payload.residents[0].elfie_id == "elfie-1"
    assert event.payload.residents[0].current_zone_id == "dorm-01"
