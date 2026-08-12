"""Orientation projection and unknown/provenance semantics."""

from datetime import datetime, timezone

from elfie.brain.orientation.system import OrientationSystem
from elfie.brain.reasoning.context_types import (
    BodyCapabilityDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.state_lifecycle import StateCommitStatus
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    EmbodiedScope,
    ExternalExecutionDomain,
    PerceptionEvent,
    PerceptionStateUpdate,
    PhysicalModality,
    PhysicalPayload,
    ResponseScope,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
    TurnId,
)

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("orientation-elfie")


def _meta(event_id: str, source: ActorRef) -> MessageMeta:
    return MessageMeta(
        event_id=EventId(event_id),
        elfie_id=ELFIE_ID,
        source=source,
        occurred_at=NOW,
        received_at=NOW,
        trace_id=TraceId("orientation-trace"),
    )


def _capabilities() -> EffectiveCapabilities:
    return EffectiveCapabilities(
        revision=1,
        captured_at=NOW,
        current_body=BodyCapabilityDescriptor(
            body_id="body-1",
            body_generation=3,
            capability_revision=1,
            sensors=("vision", "utterance"),
            actions=("walk", "speech.say"),
        ),
        connected_channels=(),
    )


def _embodied_frame() -> TurnFrame:
    actor = ActorRef(actor_id=ActorId("neighbor"), source_kind="room")
    return TurnFrame(
        frame_id=EventId("frame-embodied"),
        elfie_id=ELFIE_ID,
        revision=1,
        captured_at=NOW,
        cutoff_seq=2,
        trigger_reason=TriggerReason.SALIENCE,
        source_domain=SourceDomain.EMBODIED,
        interaction_scope=EmbodiedScope(body_id="body-1", body_generation=3),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.NERVOUS_SYSTEM,
            body_id="body-1",
            body_generation=3,
        ),
        events=(
            PerceptionEvent(
                meta=_meta("room-call", actor),
                payload=PhysicalPayload(
                    type="physical",
                    body_id="body-1",
                    body_generation=3,
                    modality=PhysicalModality.UTTERANCE,
                    content="come here",
                ),
            ),
        ),
        state_updates=(
            PerceptionStateUpdate(
                meta=_meta("location-1", actor),
                body_id="body-1",
                body_generation=3,
                state_key="body:body-1:orientation:location",
                revision=1,
                value="dorm-01",
            ),
        ),
    )


def test_embodied_observation_commits_current_body_location_and_actor() -> None:
    system = OrientationSystem(initial_at=NOW)

    snapshot, receipt = system.observe(
        frame=_embodied_frame(),
        capabilities=_capabilities(),
        turn_id=TurnId("turn-1"),
        captured_at=NOW,
    )

    assert receipt.status is StateCommitStatus.COMMITTED
    assert snapshot.revision == 1
    assert snapshot.current_turn_id == TurnId("turn-1")
    assert snapshot.body_id == "body-1"
    assert snapshot.body_generation == 3
    assert snapshot.location == "dorm-01"
    assert snapshot.location_source == "observation"
    assert snapshot.nearby_actors[0].actor_id == ActorId("neighbor")
    assert snapshot.affordances == ("walk", "speech.say")
    assert "activity" in snapshot.unknown_fields


def test_orientation_uses_the_current_activity_owned_by_activity_system() -> None:
    system = OrientationSystem(initial_at=NOW)

    snapshot, _receipt = system.observe(
        frame=_embodied_frame(),
        capabilities=_capabilities(),
        turn_id=TurnId("turn-activity"),
        captured_at=NOW,
        activity_id="activity-1",
    )

    assert snapshot.activity_id == "activity-1"
    assert "activity" not in snapshot.unknown_fields


def test_orientation_does_not_invent_nearby_people_for_a_chat_turn() -> None:
    system = OrientationSystem(initial_at=NOW)
    system.observe(
        frame=_embodied_frame(),
        capabilities=_capabilities(),
        turn_id=TurnId("turn-embodied"),
        captured_at=NOW,
    )
    frame = _embodied_frame().model_copy(
        update={
            "frame_id": EventId("frame-chat"),
            "source_domain": SourceDomain.COMMUNICATION,
            "interaction_scope": CommunicationScope(
                channel_id="chat", conversation_id="conversation-1"
            ),
            "response_scope": ResponseScope(
                external_domain=ExternalExecutionDomain.COMMUNICATION,
                channel_id="chat",
                conversation_id="conversation-1",
            ),
            "events": (),
            "state_updates": (),
        }
    )
    snapshot, _receipt = system.observe(
        frame=frame,
        capabilities=_capabilities(),
        turn_id=TurnId("turn-chat"),
        captured_at=NOW,
    )

    assert snapshot.active_channel_id == "chat"
    assert snapshot.active_conversation_id == "conversation-1"
    assert snapshot.nearby_actors[0].actor_id == ActorId("neighbor")
    assert "nearby_actors" in snapshot.unknown_fields
    assert snapshot.location == "dorm-01"
    assert "location_freshness" in snapshot.unknown_fields
    assert snapshot.freshness == "stale"
