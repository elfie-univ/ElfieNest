from unittest.mock import MagicMock

import pytest

from app.orchestration.nest_session import (
    ElfieNestEngine,
    RuntimeConnection,
    WorldEvent,
    WorldEventName,
)
from app.orchestration.nest_session.models import (
    EnvironmentState,
    ResidentMirror,
    SceneManifest,
    SemanticWorldCatalog,
    SpeechReach,
    VisualObservation,
    WorldAnchor,
    WorldConfigured,
    WorldEventPayload,
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
            _event(
                WorldEventName.WORLD_CONFIGURED,
                WorldConfigured(True, True),
            ),
        )
    )

    engine.tick_once(0.0)

    assert runtime.configurations == [("local-nest", 4, 1)]
    assert runtime.configured_revisions == [1]
    assert len(runtime.actor_syncs) == 1
    actors, revision = runtime.actor_syncs[0]
    assert revision == 1
    assert [actor.actor_id for actor in actors] == ["dog-1", "fox-1"]
    assert {actor.spawn_anchor_id for actor in actors} == {
        "dorm-01/bed-01",
        "dorm-01/bed-02",
    }


@pytest.mark.parametrize(
    ("configured", "navigation_ready"),
    ((False, True), (True, False)),
)
def test_runtime_does_not_sync_actors_before_world_is_fully_configured(
    configured: bool,
    navigation_ready: bool,
) -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    runtime.events.extend(
        (
            _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
            _event(
                WorldEventName.WORLD_CONFIGURED,
                WorldConfigured(configured, navigation_ready),
            ),
        )
    )

    engine.tick_once(0.0)

    assert runtime.configured_revisions == []
    assert runtime.actor_syncs == []


def test_matching_snapshot_updates_only_transient_resident_mirror() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    runtime.events.extend(
        (
            _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
            _event(
                WorldEventName.WORLD_CONFIGURED,
                WorldConfigured(True, True),
            ),
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


def test_speech_reach_uses_nest_semantic_interaction() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(
            WorldEventName.WORLD_CONFIGURED,
            WorldConfigured(True, True),
        ),
    ):
        engine.session.consume_runtime_event(event)
    assert engine.nest.queue_speech(
        command_id="speech-1",
        sender_id="fox-1",
        text="你好",
    )
    speech = _event(
        WorldEventName.SPEECH_REACH,
        SpeechReach(
            command_id="speech-1",
            actor_id="fox-1",
            zone_id="dorm-01",
            audience_actor_ids=("dog-1",),
        ),
        event_id="speech-event",
    )
    engine.session.consume_runtime_event(speech)

    assert engine.nest.consume_speech_events("dog-1") == (
        {
            "event_id": "speech-event:dog-1",
            "sender_id": "fox-1",
            "text": "你好",
        },
    )
    envelope = engine.nest.drain_event_outbox()
    assert len(envelope) == 1
    assert envelope[0].target_ids == ("dog-1",)
    assert envelope[0].runtime_id == "runtime-a"
    assert engine.nest.complete_speech_reach(
        command_id="speech-1",
        audience_ids=("dog-1",),
        event_id="speech-event",
    ) is None


def test_visual_observation_uses_nest_correlation_and_returns_semantic_input() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))
    runtime.events.extend(
        (
            _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
            _event(WorldEventName.WORLD_CONFIGURED, WorldConfigured(True, True)),
        )
    )
    engine.tick_once(0.0)

    assert engine.session.prepare_visual_observation(
        {
            "observation_id": "vision-1",
            "actor_id": "fox-1",
            "max_results": 4,
        }
    )
    assert runtime.visual_observation_requests == [("vision-1", "fox-1", 4, 1)]
    engine.session.consume_runtime_event(
        _event(
            WorldEventName.VISUAL_OBSERVATION,
            VisualObservation(
                observation_id="vision-1",
                actor_id="fox-1",
                zone_id="dorm-01",
                visible_semantic_ids=("actor/dog-1", "anchor/dorm-01/bed-01"),
            ),
            event_id="vision-event",
        )
    )

    visual = engine.nest.consume_visual_events("fox-1")
    assert visual[0]["event_id"] == "vision-event:fox-1"
    assert "dog-1<actor/dog-1>" in visual[0]["description"]


def test_environment_desired_state_syncs_once_and_accepts_actual_runtime_fact() -> None:
    from nest.public import EnvironmentActualState, EnvironmentDesiredState

    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.nest.set_desired_environment(
        EnvironmentDesiredState(lights_on=False, quiet_mode=True)
    )
    runtime.events.extend(
        (
            _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
            _event(WorldEventName.WORLD_CONFIGURED, WorldConfigured(True, True)),
        )
    )

    engine.tick_once(0.0)
    engine.tick_once(0.0)

    assert len(runtime.environment_requests) == 1
    _, lights_on, quiet_mode, revision = runtime.environment_requests[0]
    assert (lights_on, quiet_mode, revision) == (False, True, 1)
    engine.session.consume_runtime_event(
        _event(
            WorldEventName.ENVIRONMENT_STATE,
            EnvironmentState(
                command_id=runtime.environment_requests[0][0],
                lights_on=False,
                quiet_mode=True,
                applied=True,
            ),
            event_id="environment-event",
        )
    )
    assert engine.nest.actual_environment == EnvironmentActualState(
        command_id=runtime.environment_requests[0][0],
        lights_on=False,
        quiet_mode=True,
        applied=True,
    )


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
        _event(
            WorldEventName.WORLD_CONFIGURED,
            WorldConfigured(True, True),
        ),
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
            _event(
                WorldEventName.WORLD_CONFIGURED,
                WorldConfigured(True, True),
            ),
        )
    )

    engine.tick_once(0.0)

    assert engine.nest.state.reconciliation_required is True
    assert runtime.actor_syncs == []


def test_stale_snapshot_does_not_cross_configured_revision() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(
            WorldEventName.WORLD_CONFIGURED,
            WorldConfigured(True, True),
        ),
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
