from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.orchestration.engine import ElfieNestEngine
from app.orchestration.scene_manifest import parse_scene_manifest
from elfie import Elfie
from nest.godot_gateway.messages import (
    CommandName,
    EventName,
    RuntimeEventFrame,
)
from nest.state.models import PersistentResidentState, WorldCatalog
from nest.state.repository import (
    NestPersistenceError,
    NestPersistenceSnapshot,
)
from nest.state.store import ReconciliationRequiredError


class FakeRuntimeGateway:
    def __init__(self) -> None:
        self.runtime_connection = None
        self.commands: list[tuple[CommandName, dict[str, object], int]] = []
        self.events: list[RuntimeEventFrame] = []

    def mark_runtime_ready(
        self,
        connection: object,
        *,
        world_revision: int,
    ) -> None:
        _ = connection, world_revision

    def send_runtime_command(
        self,
        name: CommandName,
        payload: dict[str, object],
        *,
        world_revision: int,
        correlation_id: str | None = None,
    ) -> str | None:
        _ = correlation_id
        if self.runtime_connection is None:
            return None
        self.commands.append((name, payload, world_revision))
        return f"command-{len(self.commands)}"

    def drain_runtime_events(self) -> tuple[RuntimeEventFrame, ...]:
        drained = tuple(self.events)
        self.events.clear()
        return drained


class FailingNestRepository:
    def load_snapshot(self) -> NestPersistenceSnapshot:
        return NestPersistenceSnapshot(
            desired_bed_count=4,
            elapsed_seconds=0.0,
            catalog=None,
            residents=(),
        )

    def save_catalog(self, _catalog: WorldCatalog) -> None:
        return

    def save_resident(self, _resident: PersistentResidentState) -> None:
        raise NestPersistenceError("injected write failure")

    def remove_resident(self, _elfie_id: str) -> None:
        return


def test_runtime_not_ready_merges_residents_into_one_complete_actor_sync() -> None:
    gateway = FakeRuntimeGateway()
    engine = ElfieNestEngine(api_server=gateway)
    fox = MagicMock(spec=Elfie)
    dog = MagicMock(spec=Elfie)

    engine.session.register_elfie("fox-1", fox)
    engine.session.register_elfie("dog-1", dog)
    assert gateway.commands == []

    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=1,
    )
    engine.tick_once(0.0)
    assert [command[0] for command in gateway.commands] == [CommandName.CONFIGURE_WORLD]

    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, _manifest(), revision=1),
            _event(EventName.WORLD_READY, {"ready": True}, revision=1),
        ]
    )
    engine.tick_once(0.0)

    assert [command[0] for command in gateway.commands] == [
        CommandName.CONFIGURE_WORLD,
        CommandName.SYNC_ACTORS,
    ]
    actors = gateway.commands[-1][1]["actors"]
    assert [actor["actor_id"] for actor in actors] == ["dog-1", "fox-1"]
    assert {actor["home_anchor_id"] for actor in actors} == {
        "dorm-01/bed-01",
        "dorm-01/bed-02",
    }
    assert engine.nest.home_anchor_id("fox-1") is not None
    assert not hasattr(engine.nest.state, "elfies")


def test_runtime_events_do_not_mutate_state_until_tick_drain() -> None:
    gateway = FakeRuntimeGateway()
    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=2,
    )
    engine = ElfieNestEngine(api_server=gateway)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    gateway.events.append(
        _event(
            EventName.SCENE_MANIFEST,
            _manifest(),
            revision=1,
            generation=2,
        )
    )

    assert engine.nest.state.world_catalog is None
    engine.tick_once(0.0)
    assert engine.nest.state.world_catalog is not None


def test_register_rolls_back_domain_when_persistence_fails() -> None:
    gateway = FakeRuntimeGateway()
    engine = ElfieNestEngine(
        api_server=gateway,
        nest_repository=FailingNestRepository(),
    )

    try:
        engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    except NestPersistenceError:
        pass
    else:
        raise AssertionError("injected repository failure did not propagate")

    assert "fox-1" not in engine.session.elfies
    assert engine.nest.resident_state("fox-1") is None


def test_existing_resident_home_assignment_rolls_back_when_persistence_fails() -> None:
    engine = ElfieNestEngine(
        api_server=FakeRuntimeGateway(),
        nest_repository=FailingNestRepository(),
    )
    engine.nest.apply_catalog(parse_scene_manifest(_manifest()))
    engine.nest.register_resident("fox-1")

    try:
        engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    except NestPersistenceError:
        pass
    else:
        raise AssertionError("injected repository failure did not propagate")

    assert engine.nest.resident_state("fox-1") is not None
    assert engine.nest.home_anchor_id("fox-1") is None


def test_matching_world_snapshot_updates_only_runtime_mirror() -> None:
    gateway = FakeRuntimeGateway()
    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=1,
    )
    engine = ElfieNestEngine(api_server=gateway)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, _manifest(), revision=1),
            _event(EventName.WORLD_READY, {"ready": True}, revision=1),
            _event(
                EventName.WORLD_SNAPSHOT,
                {
                    "world_revision": 1,
                    "actors": [
                        {
                            "actor_id": "fox-1",
                            "zone_id": "activity-01",
                            "posture": "standing",
                            "active_command_id": None,
                        }
                    ],
                },
                revision=1,
            ),
        ]
    )

    engine.tick_once(0.0)

    mirror = engine.nest.state.runtime_mirrors["fox-1"]
    assert mirror.current_zone_id == "activity-01"
    assert engine.nest.home_anchor_id("fox-1") == "dorm-01/bed-01"


def test_runtime_speech_audience_and_tactile_contact_are_routed_once() -> None:
    gateway = FakeRuntimeGateway()
    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=1,
    )
    engine = ElfieNestEngine(api_server=gateway)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, _manifest(), revision=1),
            _event(EventName.WORLD_READY, {"ready": True}, revision=1),
        ]
    )
    engine.tick_once(0.0)
    speech = _event(
        EventName.SPEECH_AUDIENCE,
        {
            "command_id": "speech-1",
            "actor_id": "fox-1",
            "text": "你好",
            "zone_id": "dorm-01",
            "audience_actor_ids": ["dog-1", "offline-1"],
        },
        revision=1,
    )
    tactile = _event(
        EventName.TACTILE_CONTACT,
        {
            "actor_id": "dog-1",
            "intensity": 0.4,
            "direction": "front",
            "contact_kind": "actor",
            "source_semantic_id": "fox-1",
        },
        revision=1,
    )
    engine.session.consume_runtime_event(speech)
    engine.session.consume_runtime_event(tactile)
    engine.session.consume_runtime_event(tactile)

    speech_events = engine.nest.consume_speech_events("dog-1")
    assert speech_events == (
        {
            "event_id": "event-speech_audience",
            "sender_id": "fox-1",
            "text": "你好",
        },
    )
    assert engine.nest.consume_sensory_input("fox-1") == ""
    contact = engine.session.consume_tactile("dog-1")
    assert contact["intensity"] == 0.4
    assert contact["direction"] == "front"
    assert engine.session.consume_tactile("dog-1")["intensity"] == 0.0


def test_catalog_shrink_preserves_home_and_blocks_new_admission() -> None:
    gateway = FakeRuntimeGateway()
    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=1,
    )
    engine = ElfieNestEngine(api_server=gateway)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, _manifest(), revision=1),
            _event(EventName.WORLD_READY, {"ready": True}, revision=1),
        ]
    )
    engine.tick_once(0.0)
    dog_home = engine.nest.home_anchor_id("dog-1")
    reduced = _manifest()
    reduced["world_revision"] = 2
    reduced["anchors"] = reduced["anchors"][:1]
    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, reduced, revision=2),
            _event(EventName.WORLD_READY, {"ready": True}, revision=2),
        ]
    )

    engine.tick_once(0.0)

    assert engine.nest.state.reconciliation_required is True
    assert engine.nest.home_anchor_id("dog-1") == dog_home
    try:
        engine.session.register_elfie("cat-1", MagicMock(spec=Elfie))
    except ReconciliationRequiredError:
        pass
    else:
        raise AssertionError("catalog shrink did not block a new admission")
    assert engine.nest.resident_state("cat-1") is None


def test_manifest_over_capacity_marks_reconciliation_without_crashing_tick() -> None:
    gateway = FakeRuntimeGateway()
    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=1,
    )
    engine = ElfieNestEngine(api_server=gateway)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("cat-1", MagicMock(spec=Elfie))
    two_bed_manifest = _manifest()
    two_bed_manifest["anchors"] = two_bed_manifest["anchors"][:2]
    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, two_bed_manifest, revision=1),
            _event(EventName.WORLD_READY, {"ready": True}, revision=1),
        ]
    )

    engine.tick_once(0.0)

    assert engine.nest.state.reconciliation_required is True
    assert CommandName.SYNC_ACTORS not in [command[0] for command in gateway.commands]


def test_old_revision_snapshot_does_not_cross_ready_revision() -> None:
    gateway = FakeRuntimeGateway()
    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=1,
    )
    engine = ElfieNestEngine(api_server=gateway)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, _manifest(), revision=1),
            _event(EventName.WORLD_READY, {"ready": True}, revision=1),
        ]
    )
    engine.tick_once(0.0)
    gateway.events.append(
        _event(
            EventName.WORLD_SNAPSHOT,
            {
                "world_revision": 0,
                "actors": [
                    {
                        "actor_id": "fox-1",
                        "zone_id": "stale-zone",
                        "posture": "walking",
                        "active_command_id": "old-command",
                    }
                ],
            },
            revision=0,
        )
    )

    engine.tick_once(0.0)

    assert "fox-1" not in engine.nest.state.runtime_mirrors


def test_old_revision_manifest_does_not_downgrade_catalog() -> None:
    gateway = FakeRuntimeGateway()
    gateway.runtime_connection = SimpleNamespace(
        runtime_id="runtime-a",
        generation=1,
    )
    engine = ElfieNestEngine(api_server=gateway)
    gateway.events.extend(
        [
            _event(EventName.SCENE_MANIFEST, _manifest(), revision=1),
            _event(EventName.WORLD_READY, {"ready": True}, revision=1),
        ]
    )
    engine.tick_once(0.0)
    stale_manifest = _manifest()
    stale_manifest["world_revision"] = 0
    stale_manifest["zones"] = [
        {
            "zone_id": "stale-zone",
            "kind": "activity",
            "label": "stale",
            "stable_order": 0,
            "active": True,
        }
    ]
    stale_manifest["anchors"] = []
    gateway.events.append(_event(EventName.SCENE_MANIFEST, stale_manifest, revision=0))

    engine.tick_once(0.0)

    assert engine.nest.state.world_catalog is not None
    assert engine.nest.state.world_catalog.revision == 1
    assert "stale-zone" not in engine.nest.state.world_catalog.zones


def _event(
    name: EventName,
    payload: dict[str, object],
    *,
    revision: int,
    generation: int = 1,
) -> RuntimeEventFrame:
    return RuntimeEventFrame(
        protocol=2,
        kind="event",
        name=name,
        message_id=f"event-{name.value}",
        runtime_id="runtime-a",
        generation=generation,
        world_revision=revision,
        occurred_at=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        correlation_id=(
            str(payload["command_id"])
            if name
            in {
                EventName.INTENT_ACCEPTED,
                EventName.INTENT_STARTED,
                EventName.INTENT_TERMINAL,
                EventName.MOVEMENT_BLOCKED,
                EventName.SPEECH_AUDIENCE,
            }
            else None
        ),
        payload=payload,
    )


def _manifest() -> dict[str, object]:
    return {
        "nest_id": "local-nest",
        "world_revision": 1,
        "bed_count": 4,
        "zones": [
            {
                "zone_id": "dorm-01",
                "kind": "dorm",
                "label": "01 宿舍",
                "stable_order": 0,
                "active": True,
            }
        ],
        "anchors": [
            {
                "anchor_id": "dorm-01/bed-01",
                "zone_id": "dorm-01",
                "kind": "bed",
                "label": "01-01 床位",
                "stable_order": 0,
                "active": True,
            },
            {
                "anchor_id": "dorm-01/bed-02",
                "zone_id": "dorm-01",
                "kind": "bed",
                "label": "01-02 床位",
                "stable_order": 1,
                "active": True,
            },
        ],
    }
