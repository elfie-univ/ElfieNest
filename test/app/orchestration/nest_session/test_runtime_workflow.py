from unittest.mock import MagicMock

import pytest

from app.orchestration.nest_session import (
    ElfieNestEngine,
    RuntimeConnection,
    WorldEvent,
    WorldEventName,
)
from app.orchestration.nest_session.models import (
    ResidentMirror,
    SceneManifest,
    SemanticWorldCatalog,
    SpeechAudience,
    TactileContact,
    WorldAnchor,
    WorldEventPayload,
    WorldReady,
    WorldSnapshot,
    WorldZone,
)
from elfie import Elfie
from nest.state.models import PersistentResidentState
from nest.state.models import WorldCatalog as NestWorldCatalog
from nest.state.repository import NestPersistenceError, NestPersistenceSnapshot
from nest.state.store import ReconciliationRequiredError
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def test_new_runtime_restores_catalog_assigns_homes_and_syncs_all_actors() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    runtime.events.extend(
        (
            _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
            _event(WorldEventName.WORLD_READY, WorldReady(True, True)),
        )
    )

    engine.tick_once(0.0)

    assert runtime.configurations == [("local-nest", 4, 1)]
    assert runtime.ready_revisions == [1]
    assert len(runtime.actor_syncs) == 1
    actors, revision = runtime.actor_syncs[0]
    assert revision == 1
    assert [actor.actor_id for actor in actors] == ["dog-1", "fox-1"]
    assert {actor.home_anchor_id for actor in actors} == {
        "dorm-01/bed-01",
        "dorm-01/bed-02",
    }


def test_matching_snapshot_updates_only_transient_resident_mirror() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    runtime.events.extend(
        (
            _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
            _event(WorldEventName.WORLD_READY, WorldReady(True, True)),
            _event(
                WorldEventName.WORLD_SNAPSHOT,
                WorldSnapshot(
                    revision=1,
                    residents=(
                        ResidentMirror(
                            elfie_id="fox-1",
                            current_zone_id="activity-01",
                            posture="standing",
                        ),
                    ),
                ),
            ),
        )
    )

    engine.tick_once(0.0)

    mirror = engine.nest.state.runtime_mirrors["fox-1"]
    assert mirror.current_zone_id == "activity-01"
    assert engine.nest.home_anchor_id("fox-1") == "dorm-01/bed-01"


def test_speech_and_tactile_events_use_nest_semantic_interactions() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(WorldEventName.WORLD_READY, WorldReady(True, True)),
    ):
        engine.session.consume_runtime_event(event)
    speech = _event(
        WorldEventName.SPEECH_AUDIENCE,
        SpeechAudience(
            command_id="speech-1",
            actor_id="fox-1",
            text="你好",
            zone_id="dorm-01",
            audience_actor_ids=("dog-1",),
        ),
        event_id="speech-event",
    )
    tactile = _event(
        WorldEventName.TACTILE_CONTACT,
        TactileContact(
            actor_id="dog-1",
            intensity=0.4,
            direction="front",
            contact_kind="actor",
            source_semantic_id="fox-1",
        ),
        event_id="touch-event",
    )

    engine.session.consume_runtime_event(speech)
    engine.session.consume_runtime_event(tactile)
    engine.session.consume_runtime_event(tactile)

    assert engine.nest.consume_speech_events("dog-1") == (
        {"event_id": "speech-event", "sender_id": "fox-1", "text": "你好"},
    )
    assert engine.session.consume_tactile("dog-1")["intensity"] == 0.4
    assert engine.session.consume_tactile("dog-1")["intensity"] == 0.0


def test_registration_rolls_back_when_persistence_fails() -> None:
    runtime = FakeWorldRuntime()
    engine = ElfieNestEngine(runtime, nest_repository=FailingNestRepository())

    with pytest.raises(NestPersistenceError, match="injected write failure"):
        engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))

    assert engine.session.get_elfie("fox-1") is None
    assert engine.nest.resident_state("fox-1") is None


def test_catalog_shrink_preserves_existing_home_and_blocks_new_admission() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(WorldEventName.WORLD_READY, WorldReady(True, True)),
    ):
        engine.session.consume_runtime_event(event)
    dog_home = engine.nest.home_anchor_id("dog-1")

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.SCENE_MANIFEST,
            SceneManifest(_catalog(revision=2, bed_count=1)),
            revision=2,
        )
    )

    assert engine.nest.state.reconciliation_required is True
    assert engine.nest.home_anchor_id("dog-1") == dog_home
    with pytest.raises(ReconciliationRequiredError):
        engine.session.register_elfie("cat-1", MagicMock(spec=Elfie))
    assert engine.nest.resident_state("cat-1") is None


def test_manifest_below_resident_count_blocks_actor_synchronization() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    for elfie_id in ("fox-1", "dog-1", "cat-1"):
        engine.session.register_elfie(elfie_id, MagicMock(spec=Elfie))
    runtime.events.extend(
        (
            _event(
                WorldEventName.SCENE_MANIFEST,
                SceneManifest(_catalog(bed_count=2)),
            ),
            _event(WorldEventName.WORLD_READY, WorldReady(True, True)),
        )
    )

    engine.tick_once(0.0)

    assert engine.nest.state.reconciliation_required is True
    assert runtime.actor_syncs == []


def test_stale_snapshot_does_not_cross_ready_revision() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(WorldEventName.WORLD_READY, WorldReady(True, True)),
    ):
        engine.session.consume_runtime_event(event)

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.WORLD_SNAPSHOT,
            WorldSnapshot(
                revision=0,
                residents=(
                    ResidentMirror(
                        elfie_id="fox-1",
                        current_zone_id="stale-zone",
                        posture="walking",
                        active_command_id="old-command",
                    ),
                ),
            ),
            revision=0,
        )
    )

    assert "fox-1" not in engine.nest.state.runtime_mirrors


def test_stale_manifest_does_not_downgrade_catalog() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.consume_runtime_event(
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog()))
    )

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.SCENE_MANIFEST,
            SceneManifest(_catalog(revision=0, zone_id="stale-zone")),
            revision=0,
        )
    )

    assert engine.nest.state.world_catalog is not None
    assert engine.nest.state.world_catalog.revision == 1
    assert "stale-zone" not in {
        zone.zone_id for zone in engine.nest.state.world_catalog.zones
    }


def _event(
    name: WorldEventName,
    payload: WorldEventPayload,
    *,
    event_id: str = "event-1",
    revision: int = 1,
) -> WorldEvent:
    return WorldEvent(
        event_id=event_id,
        connection=RuntimeConnection("runtime-a", 1),
        world_revision=revision,
        name=name,
        payload=payload,
    )


def _catalog(
    *,
    revision: int = 1,
    bed_count: int = 4,
    zone_id: str = "dorm-01",
) -> SemanticWorldCatalog:
    return SemanticWorldCatalog(
        nest_id="local-nest",
        revision=revision,
        zones=(
            WorldZone(
                zone_id=zone_id,
                label="Dorm",
                order=0,
                anchors=tuple(
                    WorldAnchor(
                        anchor_id=f"{zone_id}/bed-{index:02d}",
                        kind="bed",
                        label=f"Bed {index}",
                        order=index - 1,
                        active=True,
                    )
                    for index in range(1, bed_count + 1)
                ),
            ),
        ),
    )


class FailingNestRepository:
    def load_snapshot(self) -> NestPersistenceSnapshot:
        return NestPersistenceSnapshot(
            desired_bed_count=4,
            elapsed_seconds=0.0,
            catalog=None,
            residents=(),
        )

    def load_home_assignments(self) -> dict[str, PersistentResidentState]:
        return {}

    def save_catalog(self, catalog: NestWorldCatalog) -> None:
        _ = catalog

    def save_resident(self, resident: PersistentResidentState) -> None:
        _ = resident
        raise NestPersistenceError("injected write failure")

    def remove_resident(self, elfie_id: str) -> None:
        _ = elfie_id
