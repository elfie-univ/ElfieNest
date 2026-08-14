"""Typed Body-to-Brain bridge tests for the NervousSystem."""

from __future__ import annotations

from threading import Event

from elfie.body import HeadlessBody
from elfie.body.contracts import (
    EmergencyStopCommand,
    EnvironmentSample,
    HeardUtterancePayload,
    ProprioceptionSample,
    SemanticActionResultPayload,
    SemanticVisualEntityPayload,
    SemanticVisualScenePayload,
    TactileImpact,
    UtteranceFinal,
    VisionSample,
)
from elfie.brain.workspace.contracts import (
    ExecutionPayload,
    IngestDisposition,
    PerceptionEvent,
    PhysicalPayload,
)
from elfie.brain.workspace.ports import PerceptionSink
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import (
    ActorId,
    EventId,
    MediaId,
    MediaRef,
    TurnId,
)
from elfie.nervous_system import NervousSystem
from test.elfie.nervous_system.perception_bridge_fixtures import (
    BODY_ID,
    ELFIE_ID,
    NOW,
    OWNER,
    ROOM,
    body_event,
    claim_all,
)


def test_receive_batch_preserves_each_utterance_and_source_identity() -> None:
    # Given: three utterances from two physically distinct speakers.
    workspace = EventWorkspace(ELFIE_ID)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
    )
    events = (
        body_event(
            "utterance-1", ROOM, UtteranceFinal(kind="utterance_final", text="左边一")
        ),
        body_event(
            "utterance-2", OWNER, UtteranceFinal(kind="utterance_final", text="主人二")
        ),
        body_event(
            "utterance-3", ROOM, UtteranceFinal(kind="utterance_final", text="左边三")
        ),
    )

    # When: the legacy batch entry delegates each typed event to the bridge.
    nervous_system.receive_body_events(events)
    frame = claim_all(workspace)

    # Then: journal order, event IDs, content, and source identity stay independent.
    assert [event.meta.event_id for event in frame.events] == [
        EventId("utterance-1"),
        EventId("utterance-2"),
        EventId("utterance-3"),
    ]
    assert [event.meta.source.actor_id for event in frame.events] == [
        ActorId("room-left"),
        ActorId("owner-near"),
        ActorId("room-left"),
    ]
    assert [event.payload.content for event in frame.events] == [
        "左边一",
        "主人二",
        "左边三",
    ]


def test_nest_semantic_payloads_enter_one_typed_embodied_perception_lane() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
    )
    nervous_system.receive_body_events(
        (
            body_event(
                "heard-1",
                ROOM,
                HeardUtterancePayload(
                    kind="heard_utterance",
                    utterance_id="speech-1",
                    sender_id="fox-1",
                    text="你好",
                    emotion="happy",
                ),
                cause_id="speech-command-1",
            ),
            body_event(
                "visual-1",
                ROOM,
                SemanticVisualScenePayload(
                    kind="semantic_visual_scene",
                    observation_id="vision-1",
                    observer_id="dog-1",
                    zone_id="room-1",
                    entities=(
                        SemanticVisualEntityPayload(
                            semantic_id="actor/fox-1",
                            kind="actor",
                            zone_id="room-1",
                            label="fox-1",
                        ),
                    ),
                ),
                cause_id="vision-observation-1",
            ),
            body_event(
                "action-1",
                ROOM,
                SemanticActionResultPayload(
                    kind="semantic_action_result",
                    command_id="move-home-1",
                    intent_id="intent-move-home-1",
                    actor_id="dog-1",
                    body_generation=1,
                    target="home",
                    resolved_anchor_id="room-1/bed-1",
                    status="completed",
                ),
                cause_id="move-intent-1",
            ),
        )
    )

    frame = claim_all(workspace)
    assert [event.meta.event_id for event in frame.events] == [
        EventId("heard-1"),
        EventId("visual-1"),
        EventId("action-1"),
    ]
    assert [event.meta.causation_id for event in frame.events] == [
        EventId("speech-command-1"),
        EventId("vision-observation-1"),
        EventId("move-intent-1"),
    ]
    contents = [event.payload.content for event in frame.events]
    assert "sender=fox-1" in contents[0] and "emotion=happy" in contents[0]
    assert "actor/fox-1" in contents[1]
    assert "status=completed" in contents[2]


def test_body_does_not_implement_the_brain_perception_sink() -> None:
    # Given: a concrete Body implementation at the physical boundary.
    body = HeadlessBody(body_id=str(BODY_ID))

    # When / Then: only NervousSystem adapters expose workspace publication.
    assert isinstance(body, PerceptionSink) is False


def test_backpressured_reliable_event_retries_once_capacity_is_available() -> None:
    # Given: a one-slot journal already occupied by a reliable utterance.
    workspace = EventWorkspace(ELFIE_ID, journal_capacity=1)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
    )
    first = body_event(
        "utterance-full", ROOM, UtteranceFinal(kind="utterance_final", text="占位")
    )
    second = body_event(
        "utterance-retry",
        OWNER,
        UtteranceFinal(kind="utterance_final", text="必须重试"),
    )
    nervous_system.receive_body_event(first)

    # When: the next reliable event is backpressured, then capacity is committed.
    nervous_system.receive_body_event(second)
    assert nervous_system.pending_count == 1
    full_frame = claim_all(workspace)
    workspace.commit(full_frame.frame_id, TurnId(f"turn-{full_frame.frame_id}"))
    nervous_system.retry_pending()
    retried_frame = claim_all(workspace)

    # Then: the pending item is removed only after retention and appears once.
    assert nervous_system.pending_count == 0
    assert [event.meta.event_id for event in retried_frame.events] == [
        EventId("utterance-retry")
    ]
    nervous_system.retry_pending()
    assert workspace.metrics().reliable_event_count == 1


def test_closed_body_perception_rejects_without_pending_growth() -> None:
    # Given: the runtime closed the Body-to-Brain input boundary.
    workspace = EventWorkspace(ELFIE_ID, journal_capacity=1)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
    )
    nervous_system.close_perception()
    event = body_event(
        "utterance-after-stop",
        ROOM,
        UtteranceFinal(kind="utterance_final", text="还在吗"),
    )

    # When: a sensor event arrives after shutdown.
    receipts = nervous_system.receive_body_event(event)

    # Then: it is rejected without entering retry state or the workspace.
    assert receipts[0].disposition is IngestDisposition.REJECTED
    assert receipts[0].reason == "body_perception_closed"
    assert nervous_system.pending_count == 0
    assert workspace.metrics().reliable_event_count == 0


def test_dangerous_touch_executes_reflex_before_cortical_publish() -> None:
    # Given: a connected body and a cortical operation that has not returned.
    workspace = EventWorkspace(ELFIE_ID, journal_capacity=16)
    body = HeadlessBody(body_id=str(BODY_ID))
    body.connect()
    cortical_returned = Event()
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
        body_port=body,
    )
    impact = body_event(
        "impact-danger",
        OWNER,
        TactileImpact(kind="tactile_impact", location="front", force_newtons=25.0),
    )

    # When: the impact crosses the reflex threshold.
    nervous_system.receive_body_event(impact)
    frames = []
    while (
        workspace.metrics().reliable_event_count or workspace.metrics().state_key_count
    ):
        frame = claim_all(workspace)
        frames.append(frame)
        workspace.commit(frame.frame_id, TurnId(f"turn-{frame.frame_id}"))

    # Then: emergency execution is already complete and stale state is observable.
    assert cortical_returned.is_set() is False
    assert isinstance(nervous_system.last_reflex_command, EmergencyStopCommand)
    snapshot = body.snapshot_body(now=NOW)
    assert snapshot.last_command_id == nervous_system.last_reflex_command.command_id
    assert nervous_system.urgent_revision == 1
    physical = [
        event
        for frame in frames
        for event in frame.events
        if isinstance(event, PerceptionEvent)
        and isinstance(event.payload, PhysicalPayload)
    ]
    execution = [
        event
        for frame in frames
        for event in frame.events
        if isinstance(event, PerceptionEvent)
        and isinstance(event.payload, ExecutionPayload)
    ]
    assert physical[0].meta.event_id == EventId("impact-danger")
    assert physical[0].meta.source.actor_id == ActorId("owner-near")
    assert "reflex emergency_stop" in physical[1].payload.content
    assert len(execution) == 3
    assert execution[-1].payload.status.value == "completed"
    assert [update.value for frame in frames for update in frame.state_updates] == [1]


def test_samples_are_routed_to_state_and_media_without_reliable_fakes() -> None:
    # Given: a camera sample plus environment and posture state samples.
    workspace = EventWorkspace(ELFIE_ID)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
    )
    media = MediaRef(
        media_id=MediaId("camera-frame-1"),
        uri="elfie-media://camera/frame-1",
        mime_type="image/jpeg",
    )
    events = (
        body_event(
            "vision-sample", ROOM, VisionSample(kind="vision_sample", media=media)
        ),
        body_event(
            "environment-sample",
            ROOM,
            EnvironmentSample(kind="environment_sample", temperature_celsius=24.0),
        ),
        body_event(
            "posture-sample",
            ROOM,
            ProprioceptionSample(
                kind="proprioception_sample", posture="sitting", arrived=True
            ),
        ),
    )

    # When: samples enter through the NervousSystem-owned endpoint.
    nervous_system.receive_body_events(events)
    frame = claim_all(workspace)

    # Then: samples update bounded zones and do not fabricate journal events.
    assert frame.events == ()
    assert [sample.media.media_id for sample in frame.media_samples] == [
        MediaId("camera-frame-1")
    ]
    assert {update.state_key for update in frame.state_updates} == {
        "body:body-nervous:environment:temperature_celsius",
        "body:body-nervous:proprioception:posture",
        "body:body-nervous:proprioception:arrived",
    }
