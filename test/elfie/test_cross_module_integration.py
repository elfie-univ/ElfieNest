"""Cross-module integration checks for the canonical typed loop."""

from __future__ import annotations

import pytest

from elfie import ElfieFactory
from elfie.body import (
    BodyId,
    BodySensorEvent,
    HeadlessBody,
    TactileImpact,
    UtteranceFinal,
)
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.state_lifecycle import StateRestoreError
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    MessageDirection,
    TextPart,
)
from elfie.diagnostics import ElfieDiagnostics
from elfie.factory import ElfieAssembly
from elfie.message_types import ActorRef, MessageMeta
from elfie.profile import create_visual_profile
from infrastructure.persistence.configuration.bundled_defaults import (
    load_reasoning_constitution,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.test_cognitive_lifecycle import (
    RecordingChannel,
    TwoTurnRuntime,
    _owner_message,
)

CONSTITUTION = ReasoningConstitution.from_mapping(load_reasoning_constitution())


def _selfhood_seed(elfie_id: str, display_name: str | None = None) -> dict[str, object]:
    return {
        "state_schema_version": 1,
        "revision": 1,
        "identity_core": {
            "elfie_id": elfie_id,
            "display_name": display_name or elfie_id,
            "species_id": "fox",
            "species_name": "Saevi",
            "home_world_id": "elfaria",
            "home_world_name": "Elfaria",
            "home_region_id": "north",
            "home_region_name": "北境",
            "earth_arrival_statement": "我被领养来到地球。",
            "resident_role": "居民",
        },
        "adaptive_self": {
            "big_five": {
                "openness": 0.91,
                "conscientiousness": 0.62,
                "extraversion": 0.21,
                "agreeableness": 0.83,
                "neuroticism": 0.31,
            },
            "interaction_tendency_ids": ["先观察边缘、声音和可离开的路径"],
            "value_ids": ["尊重自愿选择，不把猜测说成亲历。"],
            "speech_marker_ids": ["哒"],
        },
    }


def test_body_source_identity_reaches_cortical_context() -> None:
    # Given: a physical room utterance with its own source identity.
    body = HeadlessBody(body_id="cross-body")
    body.connect()
    hub = CommunicationHub("cross-elfie")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=_profile("cross-elfie"),
            selfhood_seed=_selfhood_seed("cross-elfie"),
            reasoning_constitution=CONSTITUTION,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=body,
            communication=hub,
            model_port=runtime,
        )
    )
    elfie.start()
    now = elfie.cognitive_datetime
    source = ActorRef(actor_id="room-speaker", source_kind="room")
    event = BodySensorEvent(
        event_id="room-utterance-1",
        body_id=BodyId(body.body_id),
        source=source,
        occurred_at=now,
        received_at=now,
        payload=UtteranceFinal(kind="utterance_final", text="hello from the room"),
    )

    # When: NervousSystem publishes and the Brain seals a frame.
    elfie.pump_body_events((event,))
    elfie.advance_clock(5.0)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    # Then: source identity survives into the model-neutral context.
    assert "room-speaker" in runtime.requests[0].user_prompt
    assert "hello from the room" in runtime.requests[0].user_prompt
    elfie.stop()
    elfie.join()


def test_non_owner_social_input_is_not_written_as_owner_memory() -> None:
    # Given: a peer-origin digital message on a connected channel.
    body = HeadlessBody(body_id="peer-body")
    body.connect()
    hub = CommunicationHub("peer-elfie")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=_profile("peer-elfie"),
            selfhood_seed=_selfhood_seed("peer-elfie"),
            reasoning_constitution=CONSTITUTION,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=body,
            communication=hub,
            model_port=runtime,
        )
    )
    peer = ActorRef(actor_id="peer-1", source_kind="elfie")
    now = elfie.cognitive_datetime
    envelope = CommunicationEnvelope(
        meta=MessageMeta(
            event_id="peer-message-1",
            elfie_id="peer-elfie",
            source=peer,
            occurred_at=now,
            received_at=now,
            trace_id="peer-trace-1",
        ),
        account_id="peer-account",
        channel_id="chat",
        conversation_id="peer-chat",
        sender=peer,
        recipients=(ActorRef(actor_id="peer-elfie", source_kind="elfie"),),
        direction=MessageDirection.INBOUND,
        external_message_id="peer-external-1",
        dedupe_key="peer-external-1",
        parts=(TextPart(text="peer says hello"),),
    )

    # When: the peer message completes one cognitive turn.
    elfie.start()
    elfie.receive_communication_envelope(envelope)
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    # Then: a routine peer event is completed without an unnecessary model call;
    # its owner-compatible memory remains untouched.
    assert runtime.requests == []
    assert ElfieDiagnostics(elfie).memory.get_all_episodes() == []
    elfie.stop()
    elfie.join()


def test_neutral_owner_message_does_not_drift_attachment_in_real_loop() -> None:
    hub = CommunicationHub("neutral-emotion-elfie")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=_profile("neutral-emotion-elfie"),
            selfhood_seed=_selfhood_seed("neutral-emotion-elfie"),
            reasoning_constitution=CONSTITUTION,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            communication=hub,
            model_port=runtime,
        )
    )
    emotion = ElfieDiagnostics(elfie).emotion

    elfie.start()
    elfie.receive_communication_envelope(
        _owner_message(
            elfie.cognitive_datetime,
            elfie_id="neutral-emotion-elfie",
            text="The train leaves at six.",
        )
    )
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    assert (
        emotion.get_emotion_value("happiness")
        >= emotion.parameters("happiness").baseline
    )
    assert "attachment" not in emotion.emotions
    elfie.stop()
    elfie.join()


def test_tactile_input_updates_fear_in_real_elfie_loop() -> None:
    body = HeadlessBody(body_id="emotion-body")
    body.connect()
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=_profile("embodied-emotion-elfie"),
            selfhood_seed=_selfhood_seed("embodied-emotion-elfie"),
            reasoning_constitution=CONSTITUTION,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=body,
            model_port=runtime,
        )
    )
    emotion = ElfieDiagnostics(elfie).emotion
    now = elfie.cognitive_datetime
    event = BodySensorEvent(
        event_id="touch-emotion-1",
        body_id=BodyId(body.body_id),
        source=ActorRef(actor_id="world-contact", source_kind="world"),
        occurred_at=now,
        received_at=now,
        payload=TactileImpact(
            kind="tactile_impact",
            location="front",
            intensity=0.8,
            force_newtons=5.0,
        ),
    )

    elfie.start()
    elfie.pump_body_events((event,))
    elfie.advance_clock(5.0)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    assert emotion.get_emotion_value("fear") > emotion.parameters("fear").baseline
    assert runtime.requests == []
    elfie.stop()
    elfie.join()


def test_selfhood_and_profile_anchors_are_separate_model_context_sections() -> None:
    # Given: one immutable Profile seed with a deliberately distinctive personality.
    profile = _profile("selfhood-elfie")
    selfhood_seed = _selfhood_seed("selfhood-elfie")
    hub = CommunicationHub("selfhood-elfie")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            selfhood_seed=selfhood_seed,
            reasoning_constitution=CONSTITUTION,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            communication=hub,
            model_port=runtime,
        )
    )
    elfie.start()
    elfie.receive_communication_envelope(
        _owner_message(elfie.cognitive_datetime, elfie_id="selfhood-elfie")
    )
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    # When: a source Profile mapping is changed after Brain construction.
    selfhood_seed["adaptive_self"]["big_five"]["openness"] = 0.01

    # Then: the Run still sees the immutable two-layer Brain Selfhood plus
    # external Profile anchors.
    system_prompt = runtime.requests[0].system_prompt
    user_prompt = runtime.requests[0].user_prompt
    assert "[APPLICATION_FRAME]" in system_prompt
    assert "[IDENTITY_CORE]" in system_prompt
    assert "[ADAPTIVE_SELF]" in system_prompt
    assert "[OPERATING_CONTRACT]" in system_prompt
    assert "开放性" in system_prompt
    assert "0.91" not in system_prompt
    assert '"selfhood"' not in user_prompt
    assert '"profile_anchors"' not in user_prompt
    assert elfie.selfhood_snapshot().adaptive_self.big_five.openness == 0.91
    assert elfie.profile_anchor_snapshot().display_name == "selfhood-elfie"
    elfie.stop()
    elfie.join()


def test_continuity_restores_energy_and_memory_but_emotion_restarts_fresh() -> None:
    # Given: one assembled Brain whose durable owners have committed state.
    store = SQLiteMemoryStoreAdapter.in_memory()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=_profile("continuity-elfie"),
            selfhood_seed=_selfhood_seed("continuity-elfie"),
            reasoning_constitution=CONSTITUTION,
            memory_store=store,
            model_port=TwoTurnRuntime(),
        )
    )
    ElfieDiagnostics(elfie).energy.consume_energy_by_action(token_count=100)
    ElfieDiagnostics(elfie).memory.record_episode(
        content="我把这件事记住了",
        emotion="happiness",
        intensity=80.0,
        source_event_ids=("continuity-source",),
    )
    checkpoint = elfie.continuity_checkpoint()

    # A new runtime over the same durable memory can restore that checkpoint.
    restored = ElfieFactory().create(
        ElfieAssembly(
            profile=_profile("continuity-elfie"),
            selfhood_seed=_selfhood_seed("continuity-elfie"),
            reasoning_constitution=CONSTITUTION,
            memory_store=store,
            model_port=TwoTurnRuntime(),
        )
    )
    restored.restore_continuity(checkpoint)

    # When: newer uncommitted-in-the-checkpoint state is produced.
    ElfieDiagnostics(elfie).energy.consume_energy_by_action(token_count=100)
    ElfieDiagnostics(elfie).memory.record_episode(
        content="这件事后来又发生了",
        emotion="happiness",
        intensity=80.0,
    )
    with pytest.raises(StateRestoreError):
        elfie.restore_continuity(checkpoint)

    # Then: the restarted runtime has the same committed state.
    restored_emotion = ElfieDiagnostics(restored).emotion
    assert all(
        restored_emotion.get_emotion_value(name)
        == restored_emotion.parameters(name).baseline
        for name in restored_emotion.emotions
    )
    assert ElfieDiagnostics(restored).energy.checkpoint() == checkpoint.energy
    assert ElfieDiagnostics(restored).memory.checkpoint() == checkpoint.memory


def _profile(elfie_id: str):
    return create_visual_profile(
        elfie_id=elfie_id,
        display_name=elfie_id,
        species_id="fox",
        seed=1,
    )
