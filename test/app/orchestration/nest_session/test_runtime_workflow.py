from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.orchestration.nest_session import (
    ElfieNestEngine,
    NestStateStoreError,
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
from elfie.body.contracts import (
    HeardUtterancePayload,
    NestFactNoticePayload,
    SemanticActionResultPayload,
    SemanticVisualScenePayload,
)
from nest.living_rules.errors import ReconciliationRequiredError
from nest.snapshot import NestSnapshot
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

    mirror = engine.nest.runtime_mirrors["fox-1"]
    assert mirror.current_zone_id == "activity-01"
    assert mirror.runtime_id == "runtime-a"
    assert mirror.runtime_generation == 1
    assert mirror.world_revision == 1
    assert engine.nest.home_anchor_id("fox-1") == "dorm-01/bed-01"


def test_speech_reach_uses_nest_semantic_interaction() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    fox = MagicMock(spec=Elfie)
    dog = MagicMock(spec=Elfie)
    cat = MagicMock(spec=Elfie)
    engine.session.register_elfie("fox-1", fox)
    engine.session.register_elfie("dog-1", dog)
    engine.session.register_elfie("cat-1", cat)
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(
            WorldEventName.WORLD_CONFIGURED,
            WorldConfigured(True, True),
        ),
    ):
        engine.session.consume_runtime_event(event)
    baseline_calls = {
        "fox": fox.pump_body_events.call_count,
        "dog": dog.pump_body_events.call_count,
        "cat": cat.pump_body_events.call_count,
    }
    assert engine.nest.queue_speech(
        command_id="speech-1",
        sender_id="fox-1",
        text="你好",
        emotion="happy",
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

    delivered = dog.pump_body_events.call_args.args[0]
    assert len(delivered) == 1
    event = delivered[0]
    assert isinstance(event.payload, HeardUtterancePayload)
    assert event.event_id == "speech-event"
    assert event.cause_id == "speech-1"
    assert event.payload.text == "你好"
    assert event.payload.emotion == "happy"
    assert event.payload.sender_id == "fox-1"
    assert fox.pump_body_events.call_count == baseline_calls["fox"]
    assert cat.pump_body_events.call_count == baseline_calls["cat"]
    assert dog.pump_body_events.call_count == baseline_calls["dog"] + 1
    assert engine.nest.drain_event_outbox() == ()

    # A repeated Runtime frame cannot re-deliver a consumed semantic event.
    engine.session.consume_runtime_event(speech)
    assert dog.pump_body_events.call_count == baseline_calls["dog"] + 1
    assert (
        engine.nest.complete_speech_reach(
            command_id="speech-1",
            audience_ids=("dog-1",),
            event_id="speech-event",
        )
        is None
    )


def test_owner_fact_notice_reaches_the_target_elfie_through_typed_delivery() -> None:
    from nest.time_environment.models import EnvironmentRule, LifePhase

    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    fox = MagicMock(spec=Elfie)
    engine.session.register_elfie("fox-1", fox)

    engine.nest.set_environment_rules(
        (
            EnvironmentRule(
                rule_id="quiet-night",
                phase=LifePhase.NIGHT,
                lights_on=False,
                quiet_mode=True,
            ),
        )
    )
    engine.session.consume_runtime_event(
        _event(
            WorldEventName.WORLD_CONFIGURED,
            WorldConfigured(False, False),
        )
    )

    delivered = fox.pump_body_events.call_args.args[0]
    assert len(delivered) == 2
    payloads = tuple(event.payload for event in delivered)
    assert all(isinstance(payload, NestFactNoticePayload) for payload in payloads)
    assert {payload.fact_type for payload in payloads} == {
        "environment_rule_changed",
        "environment_desired_changed",
    }
    rule_payload = next(
        payload
        for payload in payloads
        if payload.fact_type == "environment_rule_changed"
    )
    assert rule_payload.fact_id == "quiet-night"
    assert all(event.source.source_kind == "nest" for event in delivered)
    assert engine.nest.drain_event_outbox() == ()


def test_failed_target_delivery_requeues_only_that_target() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    fox = MagicMock(spec=Elfie)
    dog = MagicMock(spec=Elfie)
    cat = MagicMock(spec=Elfie)
    dog.pump_body_events.side_effect = [RuntimeError("body offline"), ()]
    engine.session.register_elfie("fox-1", fox)
    engine.session.register_elfie("dog-1", dog)
    engine.session.register_elfie("cat-1", cat)
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(WorldEventName.WORLD_CONFIGURED, WorldConfigured(True, True)),
    ):
        engine.session.consume_runtime_event(event)
    dog.pump_body_events.reset_mock()
    cat.pump_body_events.reset_mock()
    dog.pump_body_events.side_effect = [RuntimeError("body offline"), ()]
    assert engine.nest.queue_speech(
        command_id="speech-retry-1",
        sender_id="fox-1",
        text="请回来",
    )
    speech = _event(
        WorldEventName.SPEECH_REACH,
        SpeechReach(
            command_id="speech-retry-1",
            actor_id="fox-1",
            zone_id="dorm-01",
            audience_actor_ids=("dog-1", "cat-1"),
        ),
        event_id="speech-retry-event",
    )

    engine.session.consume_runtime_event(speech)
    assert dog.pump_body_events.call_count == 1
    assert cat.pump_body_events.call_count == 1

    engine.session.consume_runtime_event(speech)
    assert dog.pump_body_events.call_count == 2
    assert cat.pump_body_events.call_count == 1
    assert engine.nest.drain_event_outbox() == ()


def test_visual_observation_uses_nest_correlation_and_returns_semantic_input() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    fox = MagicMock(spec=Elfie)
    dog = MagicMock(spec=Elfie)
    engine.session.register_elfie("fox-1", fox)
    engine.session.register_elfie("dog-1", dog)
    runtime.events.extend(
        (
            _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
            _event(WorldEventName.WORLD_CONFIGURED, WorldConfigured(True, True)),
        )
    )
    engine.tick_once(0.0)
    dog_call_count = dog.pump_body_events.call_count

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

    delivered = fox.pump_body_events.call_args.args[0]
    assert len(delivered) == 1
    event = delivered[0]
    assert isinstance(event.payload, SemanticVisualScenePayload)
    assert event.event_id == "vision-event"
    assert event.cause_id == "vision-1"
    assert event.payload.observation_id == "vision-1"
    assert [entity.semantic_id for entity in event.payload.entities] == [
        "actor/dog-1",
        "anchor/dorm-01/bed-01",
    ]
    assert engine.nest.drain_event_outbox() == ()
    assert dog.pump_body_events.call_count == dog_call_count
    delivered_call_count = fox.pump_body_events.call_count

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.VISUAL_OBSERVATION,
            VisualObservation(
                observation_id="vision-1",
                actor_id="fox-1",
                zone_id="dorm-01",
                visible_semantic_ids=("actor/dog-1",),
            ),
            event_id="vision-event",
        )
    )
    assert fox.pump_body_events.call_count == delivered_call_count


def test_semantic_action_result_reaches_only_originating_elfie_once() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    fox = MagicMock(spec=Elfie)
    dog = MagicMock(spec=Elfie)
    engine.session.register_elfie("fox-1", fox)
    engine.session.register_elfie("dog-1", dog)
    engine.session.consume_runtime_event(
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog()))
    )
    fox_calls_before_action = fox.pump_body_events.call_count
    dog_calls_before_action = dog.pump_body_events.call_count
    assert engine.session.prepare_semantic_action(
        {
            "command_id": "home-1",
            "intent_id": "intent-home-1",
            "actor_id": "fox-1",
            "body_generation": 1,
            "initiator": "elfie",
            "anchor_id": "home",
        }
    ) == engine.nest.home_anchor_id("fox-1")

    engine.session.complete_semantic_action(
        {
            "command_id": "home-1",
            "actor_id": "fox-1",
            "anchor_id": "home",
        },
        SimpleNamespace(terminal_status="completed", reason="", events=()),
    )

    delivered = fox.pump_body_events.call_args.args[0]
    assert len(delivered) == 1
    event = delivered[0]
    assert isinstance(event.payload, SemanticActionResultPayload)
    assert event.event_id == "semantic-action:home-1"
    assert event.cause_id == "home-1"
    assert event.payload.intent_id == "intent-home-1"
    assert event.payload.body_generation == 1
    assert event.payload.resolved_anchor_id == engine.nest.home_anchor_id("fox-1")
    assert event.payload.status == "completed"
    assert fox.pump_body_events.call_count == fox_calls_before_action + 1
    assert dog.pump_body_events.call_count == dog_calls_before_action
    assert engine.nest.drain_event_outbox() == ()

    engine.session.complete_semantic_action(
        {
            "command_id": "home-1",
            "actor_id": "fox-1",
            "anchor_id": "home",
        },
        SimpleNamespace(terminal_status="completed", reason="", events=()),
    )
    assert fox.pump_body_events.call_count == fox_calls_before_action + 1


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
    object_id, _, lights_on, quiet_mode, revision = runtime.environment_requests[0]
    assert object_id == "nest/environment"
    assert (lights_on, quiet_mode, revision) == (False, True, 1)
    engine.session.consume_runtime_event(
        _event(
            WorldEventName.ENVIRONMENT_STATE,
            EnvironmentState(
                object_id="nest/environment",
                command_id=runtime.environment_requests[0][1],
                lights_on=False,
                quiet_mode=True,
                applied=True,
            ),
            event_id="environment-event",
        )
    )
    assert engine.nest.actual_environment == EnvironmentActualState(
        object_id="nest/environment",
        command_id=runtime.environment_requests[0][1],
        lights_on=False,
        quiet_mode=True,
        applied=True,
        runtime_id="runtime-a",
        runtime_generation=1,
        world_revision=1,
    )


def test_registration_rolls_back_when_persistence_fails() -> None:
    runtime = FakeWorldRuntime()
    engine = ElfieNestEngine(runtime, state_store=FailingNestStateStore())

    with pytest.raises(NestStateStoreError, match="injected write failure"):
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

    assert engine.nest.reconciliation_required is True
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

    assert engine.nest.reconciliation_required is True
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

    assert "fox-1" not in engine.nest.runtime_mirrors


def test_runtime_generation_change_invalidates_projections_and_pending_work() -> None:
    from nest.public import EnvironmentActualState, EnvironmentDesiredState

    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    fox = MagicMock(spec=Elfie)
    dog = MagicMock(spec=Elfie)
    fox_transport = MagicMock()
    fox.current_body = MagicMock(transport=fox_transport)
    engine.session.register_elfie("fox-1", fox)
    engine.session.register_elfie("dog-1", dog)
    engine.session.poll_runtime_connection()
    initial_interrupt_count = fox_transport.interrupt_pending.call_count
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(WorldEventName.WORLD_CONFIGURED, WorldConfigured(True, True)),
        _event(
            WorldEventName.WORLD_SNAPSHOT,
            WorldSnapshot(
                revision=1,
                residents=(
                    ResidentMirror(
                        elfie_id="fox-1",
                        current_zone_id="dorm-01",
                        posture="standing",
                    ),
                ),
            ),
        ),
        _event(
            WorldEventName.ENVIRONMENT_STATE,
            EnvironmentState(
                object_id="nest/environment",
                command_id="environment-old",
                lights_on=False,
                quiet_mode=True,
                applied=True,
            ),
            event_id="environment-old-event",
        ),
    ):
        engine.session.consume_runtime_event(event)

    engine.nest.set_desired_environment(
        EnvironmentDesiredState(lights_on=False, quiet_mode=True)
    )
    assert engine.nest.runtime_mirrors
    assert engine.nest.actual_environment == EnvironmentActualState(
        object_id="nest/environment",
        command_id="environment-old",
        lights_on=False,
        quiet_mode=True,
        applied=True,
        runtime_id="runtime-a",
        runtime_generation=1,
        world_revision=1,
    )
    assert engine.nest.queue_speech(
        command_id="speech-old",
        sender_id="fox-1",
        text="旧 Runtime 内容",
    )
    assert engine.nest.queue_visual_observation(
        observation_id="visual-old",
        observer_id="fox-1",
    )
    assert engine.session.prepare_semantic_action(
        {
            "command_id": "action-old",
            "intent_id": "intent-action-old",
            "actor_id": "fox-1",
            "body_generation": 1,
            "initiator": "elfie",
            "anchor_id": "home",
        }
    ) == engine.nest.home_anchor_id("fox-1")

    runtime.connection = RuntimeConnection("runtime-b", 2)
    engine.session.poll_runtime_connection()

    assert fox_transport.interrupt_pending.call_count == initial_interrupt_count + 1
    assert engine.nest.runtime_mirrors == {}
    assert engine.nest.actual_environment is None
    assert (
        engine.nest.complete_speech_reach(
            command_id="speech-old",
            audience_ids=("dog-1",),
            event_id="speech-old-event",
        )
        is None
    )
    assert (
        engine.nest.complete_visual_observation(
            observation_id="visual-old",
            zone_id="dorm-01",
            visible_semantic_ids=(),
            event_id="visual-old-event",
        )
        is None
    )
    assert (
        engine.nest.complete_semantic_action(
            command_id="action-old",
            status="completed",
            reason=None,
            event_id="action-old-event",
        )
        is None
    )

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.WORLD_SNAPSHOT,
            WorldSnapshot(
                revision=1,
                residents=(
                    ResidentMirror(
                        elfie_id="fox-1",
                        current_zone_id="stale-zone",
                        posture="walking",
                    ),
                ),
            ),
            runtime_id="runtime-a",
            generation=1,
        )
    )
    assert engine.nest.runtime_mirrors == {}

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.SCENE_MANIFEST,
            SceneManifest(_catalog()),
            runtime_id="runtime-b",
            generation=2,
        )
    )
    engine.session.consume_runtime_event(
        _event(
            WorldEventName.WORLD_CONFIGURED,
            WorldConfigured(True, True),
            runtime_id="runtime-b",
            generation=2,
        )
    )
    engine.session.flush_environment_state()
    assert runtime.environment_requests[-1][2:] == (False, True, 1)

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.WORLD_SNAPSHOT,
            WorldSnapshot(
                revision=1,
                residents=(
                    ResidentMirror(
                        elfie_id="fox-1",
                        current_zone_id="dorm-01",
                        posture="standing",
                    ),
                ),
            ),
            runtime_id="runtime-b",
            generation=2,
        )
    )
    mirror = engine.nest.runtime_mirrors["fox-1"]
    assert (mirror.runtime_id, mirror.runtime_generation, mirror.world_revision) == (
        "runtime-b",
        2,
        1,
    )


def test_manifest_revision_change_invalidates_old_runtime_state() -> None:
    from nest.public import EnvironmentDesiredState

    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    engine = ElfieNestEngine(runtime)
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.poll_runtime_connection()
    for event in (
        _event(WorldEventName.SCENE_MANIFEST, SceneManifest(_catalog())),
        _event(WorldEventName.WORLD_CONFIGURED, WorldConfigured(True, True)),
        _event(
            WorldEventName.WORLD_SNAPSHOT,
            WorldSnapshot(
                revision=1,
                residents=(
                    ResidentMirror(
                        elfie_id="fox-1",
                        current_zone_id="dorm-01",
                        posture="standing",
                    ),
                ),
            ),
        ),
    ):
        engine.session.consume_runtime_event(event)
    assert engine.nest.queue_speech(
        command_id="speech-revision-old",
        sender_id="fox-1",
        text="旧 revision 内容",
    )
    assert engine.nest.runtime_mirrors
    engine.nest.set_desired_environment(
        EnvironmentDesiredState(lights_on=False, quiet_mode=True)
    )

    engine.session.consume_runtime_event(
        _event(
            WorldEventName.SCENE_MANIFEST,
            SceneManifest(_catalog(revision=2)),
            revision=2,
        )
    )

    assert engine.nest.runtime_mirrors == {}
    assert engine.nest.actual_environment is None
    assert (
        engine.nest.complete_speech_reach(
            command_id="speech-revision-old",
            audience_ids=(),
            event_id="speech-revision-old-event",
        )
        is None
    )
    engine.session.consume_runtime_event(
        _event(
            WorldEventName.WORLD_CONFIGURED,
            WorldConfigured(True, True),
            revision=2,
        )
    )
    engine.session.flush_environment_state()
    assert runtime.environment_requests[-1][4] == 2
    engine.session.consume_runtime_event(
        _event(
            WorldEventName.WORLD_SNAPSHOT,
            WorldSnapshot(
                revision=1,
                residents=(
                    ResidentMirror(
                        elfie_id="fox-1",
                        current_zone_id="stale-zone",
                        posture="walking",
                    ),
                ),
            ),
            revision=1,
        )
    )
    assert engine.nest.runtime_mirrors == {}


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

    assert engine.nest.world_catalog is not None
    assert engine.nest.world_catalog.revision == 1
    assert "stale-zone" not in {
        zone.zone_id for zone in engine.nest.world_catalog.zones
    }


def _event(
    name: WorldEventName,
    payload: WorldEventPayload,
    *,
    event_id: str = "event-1",
    revision: int = 1,
    runtime_id: str = "runtime-a",
    generation: int = 1,
) -> WorldEvent:
    return WorldEvent(
        event_id=event_id,
        connection=RuntimeConnection(runtime_id, generation),
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


class FailingNestStateStore:
    def load_snapshot(self) -> NestSnapshot:
        return NestSnapshot(
            desired_bed_count=4,
            elapsed_seconds=0.0,
            catalog=None,
            residents=(),
        )

    def save_snapshot(self, snapshot: NestSnapshot) -> None:
        _ = snapshot
        raise NestStateStoreError("injected write failure")
