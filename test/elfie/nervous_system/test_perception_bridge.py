"""Typed Body-to-Brain bridge tests for the NervousSystem."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock

from elfie import Elfie
from elfie.body import HeadlessBody
from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    EmergencyStopCommand,
    EnvironmentSample,
    ProprioceptionSample,
    TactileImpact,
    UtteranceFinal,
    VisionSample,
)
from elfie.brain.perception_types import (
    ExecutionPayload,
    IngestDisposition,
    IngestReceipt,
    PerceptionEvent,
    PerceptionWrite,
    PhysicalPayload,
    TriggerReason,
)
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.workspace_ports import PerceptionSink
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MediaId,
    MediaRef,
    TurnId,
)
from elfie.nervous_system import NervousSystem

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-nervous")
BODY_ID = BodyId("body-nervous")
OWNER = ActorRef(actor_id=ActorId("owner-near"), source_kind="microphone")
ROOM = ActorRef(actor_id=ActorId("room-left"), source_kind="microphone")


def _body_event(
    event_id: str,
    source: ActorRef,
    payload: (
        UtteranceFinal
        | VisionSample
        | TactileImpact
        | ProprioceptionSample
        | EnvironmentSample
    ),
) -> BodySensorEvent:
    return BodySensorEvent(
        event_id=EventId(event_id),
        body_id=BODY_ID,
        source=source,
        occurred_at=NOW,
        received_at=NOW,
        payload=payload,
    )


def _claim_all(workspace: PerceptualWorkspace):
    frame_id = workspace.seal(reason=TriggerReason.MANUAL, captured_at=NOW)
    assert frame_id is not None
    return workspace.claim(frame_id, TurnId(f"turn-{frame_id}"))


def test_receive_batch_preserves_each_utterance_and_source_identity() -> None:
    # Given: three utterances from two physically distinct speakers.
    workspace = PerceptualWorkspace(ELFIE_ID)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
    )
    events = (
        _body_event(
            "utterance-1", ROOM, UtteranceFinal(kind="utterance_final", text="左边一")
        ),
        _body_event(
            "utterance-2", OWNER, UtteranceFinal(kind="utterance_final", text="主人二")
        ),
        _body_event(
            "utterance-3", ROOM, UtteranceFinal(kind="utterance_final", text="左边三")
        ),
    )

    # When: the legacy batch entry delegates each typed event to the bridge.
    nervous_system.receive_body_events(events)
    frame = _claim_all(workspace)

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


def test_body_does_not_implement_the_brain_perception_sink() -> None:
    # Given: a concrete Body implementation at the physical boundary.
    body = HeadlessBody(body_id=str(BODY_ID))

    # When / Then: only NervousSystem adapters expose workspace publication.
    assert isinstance(body, PerceptionSink) is False


def test_backpressured_reliable_event_retries_once_capacity_is_available() -> None:
    # Given: a one-slot journal already occupied by a reliable utterance.
    workspace = PerceptualWorkspace(ELFIE_ID, journal_capacity=1)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
    )
    first = _body_event(
        "utterance-full", ROOM, UtteranceFinal(kind="utterance_final", text="占位")
    )
    second = _body_event(
        "utterance-retry",
        OWNER,
        UtteranceFinal(kind="utterance_final", text="必须重试"),
    )
    nervous_system.receive_body_event(first)

    # When: the next reliable event is backpressured, then capacity is committed.
    nervous_system.receive_body_event(second)
    assert nervous_system.pending_count == 1
    full_frame = _claim_all(workspace)
    workspace.commit(full_frame.frame_id, TurnId(f"turn-{full_frame.frame_id}"))
    nervous_system.retry_pending()
    retried_frame = _claim_all(workspace)

    # Then: the pending item is removed only after retention and appears once.
    assert nervous_system.pending_count == 0
    assert [event.meta.event_id for event in retried_frame.events] == [
        EventId("utterance-retry")
    ]
    nervous_system.retry_pending()
    assert workspace.metrics().reliable_event_count == 1


def test_dangerous_touch_executes_reflex_before_cortical_publish() -> None:
    # Given: a connected body and a cortical operation that has not returned.
    workspace = PerceptualWorkspace(ELFIE_ID, journal_capacity=16)
    body = HeadlessBody(body_id=str(BODY_ID))
    body.connect()
    cortical_returned = Event()
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
        body_port=body,
    )
    impact = _body_event(
        "impact-danger",
        OWNER,
        TactileImpact(kind="tactile_impact", location="front", force_newtons=25.0),
    )

    # When: the impact crosses the reflex threshold.
    nervous_system.receive_body_event(impact)
    frame = _claim_all(workspace)

    # Then: emergency execution is already complete and stale state is observable.
    assert cortical_returned.is_set() is False
    assert isinstance(nervous_system.last_reflex_command, EmergencyStopCommand)
    snapshot = body.snapshot_body(now=NOW)
    assert snapshot.last_command_id == nervous_system.last_reflex_command.command_id
    assert nervous_system.urgent_revision == 1
    physical = [
        event
        for event in frame.events
        if isinstance(event, PerceptionEvent)
        and isinstance(event.payload, PhysicalPayload)
    ]
    execution = [
        event
        for event in frame.events
        if isinstance(event, PerceptionEvent)
        and isinstance(event.payload, ExecutionPayload)
    ]
    assert physical[0].meta.event_id == EventId("impact-danger")
    assert physical[0].meta.source.actor_id == ActorId("owner-near")
    assert "reflex emergency_stop" in physical[1].payload.content
    assert len(execution) == 3
    assert execution[-1].payload.status.value == "completed"
    assert [update.value for update in frame.state_updates] == [1]


def test_samples_are_routed_to_state_and_media_without_reliable_fakes() -> None:
    # Given: a camera sample plus environment and posture state samples.
    workspace = PerceptualWorkspace(ELFIE_ID)
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
        _body_event(
            "vision-sample", ROOM, VisionSample(kind="vision_sample", media=media)
        ),
        _body_event(
            "environment-sample",
            ROOM,
            EnvironmentSample(kind="environment_sample", temperature_celsius=24.0),
        ),
        _body_event(
            "posture-sample",
            ROOM,
            ProprioceptionSample(
                kind="proprioception_sample", posture="sitting", arrived=True
            ),
        ),
    )

    # When: samples enter through the NervousSystem-owned endpoint.
    nervous_system.receive_body_events(events)
    frame = _claim_all(workspace)

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


def test_concurrent_body_producers_publish_each_reliable_event_once() -> None:
    # Given: two producers reach a sink publication at the same time.
    class CoordinatedSink:
        def __init__(self) -> None:
            self.lock = Lock()
            self.event_ids = []
            self.sequence = 0

        def publish(self, write: PerceptionWrite) -> IngestReceipt:
            with self.lock:
                self.sequence += 1
                self.event_ids.append(write.meta.event_id)
                sequence = self.sequence
            return IngestReceipt(
                event_id=write.meta.event_id,
                disposition=IngestDisposition.ACCEPTED,
                ingest_seq=sequence,
                retryable=False,
                reason=None,
            )

    sink = CoordinatedSink()
    nervous_system = NervousSystem(perception_sink=sink, elfie_id=ELFIE_ID)
    events = (
        _body_event(
            "concurrent-1",
            ROOM,
            UtteranceFinal(kind="utterance_final", text="第一条"),
        ),
        _body_event(
            "concurrent-2",
            OWNER,
            UtteranceFinal(kind="utterance_final", text="第二条"),
        ),
    )

    # When: both producers publish concurrently.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(pool.submit(nervous_system.receive_body_event, event) for event in events)
        tuple(future.result() for future in futures)

    # Then: neither event is duplicated or removed by the other producer.
    assert sorted(sink.event_ids) == [EventId("concurrent-1"), EventId("concurrent-2")]
    assert nervous_system.pending_count == 0


def test_reentrant_sink_observes_pending_state_without_deadlock() -> None:
    # Given: a sink calls back into retry while its current publish is active.
    class ReentrantSink:
        nervous_system: NervousSystem | None = None
        nested_retry_count = -1

        def publish(self, write: PerceptionWrite) -> IngestReceipt:
            nervous_system = self.nervous_system
            assert nervous_system is not None
            self.nested_retry_count = len(nervous_system.retry_pending())
            return IngestReceipt(
                event_id=write.meta.event_id,
                disposition=IngestDisposition.ACCEPTED,
                ingest_seq=1,
                retryable=False,
                reason=None,
            )

    sink = ReentrantSink()
    nervous_system = NervousSystem(perception_sink=sink, elfie_id=ELFIE_ID)
    sink.nervous_system = nervous_system

    # When: one reliable event enters the bridge.
    nervous_system.receive_body_event(
        _body_event(
            "reentrant-event",
            ROOM,
            UtteranceFinal(kind="utterance_final", text="可重入"),
        )
    )

    # Then: the nested retry yields to the active owner and the event commits.
    assert sink.nested_retry_count == 0
    assert nervous_system.pending_count == 0


def test_humidity_and_illuminance_changes_publish_without_temperature_change() -> None:
    # Given: an initial environment sample has already been committed.
    workspace = PerceptualWorkspace(ELFIE_ID)
    nervous_system = NervousSystem(perception_sink=workspace, elfie_id=ELFIE_ID)
    nervous_system.receive_body_event(
        _body_event(
            "environment-initial",
            ROOM,
            EnvironmentSample(
                kind="environment_sample",
                temperature_celsius=24.0,
                humidity_ratio=0.40,
                illuminance_lux=100.0,
            ),
        )
    )
    initial = _claim_all(workspace)
    workspace.commit(initial.frame_id, TurnId(f"turn-{initial.frame_id}"))

    # When: only humidity and illuminance change.
    nervous_system.receive_body_event(
        _body_event(
            "environment-changed",
            ROOM,
            EnvironmentSample(
                kind="environment_sample",
                temperature_celsius=24.0,
                humidity_ratio=0.55,
                illuminance_lux=180.0,
            ),
        )
    )
    changed = _claim_all(workspace)

    # Then: both independently changed state values are retained.
    assert {update.state_key for update in changed.state_updates} == {
        "body:body-nervous:environment:humidity_ratio",
        "body:body-nervous:environment:illuminance_lux",
    }


def test_elfie_body_switch_updates_the_reflex_execution_target() -> None:
    # Given: an Elfie binds one body and then switches to another.
    elfie = Elfie(memory_db_path=":memory:")
    old_body = HeadlessBody(body_id="old-body")
    current_body = HeadlessBody(body_id="current-body")
    elfie.register_body(old_body, make_current=True)
    elfie.register_body(current_body)
    elfie.bind_body(current_body.body_id)
    impact = BodySensorEvent(
        event_id=EventId("switched-impact"),
        body_id=BodyId(current_body.body_id),
        source=OWNER,
        occurred_at=NOW,
        received_at=NOW,
        payload=TactileImpact(
            kind="tactile_impact",
            location="front",
            force_newtons=25.0,
        ),
    )

    # When: the current body reports a dangerous impact.
    elfie.nervous_system.receive_body_event(impact)

    # Then: only the newly bound body executes the emergency stop.
    assert current_body.snapshot_body(now=NOW).last_command_id is not None
    assert old_body.snapshot_body(now=NOW).last_command_id is None
