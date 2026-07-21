"""Thread-safe lifecycle tests for the Brain perceptual workspace."""

from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock, Thread

import pytest

from elfie.brain.perception_types import (
    IngestDisposition,
    InternalSignal,
    PerceptionEvent,
    PerceptionFrame,
    PerceptionMediaSample,
    PerceptionStateUpdate,
    PhysicalModality,
    PhysicalPayload,
    TriggerReason,
)
from elfie.brain.perceptual_workspace import (
    ActiveClaimError,
    PerceptualWorkspace,
    ProcessingFailureEvent,
    WaitStatus,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MediaId,
    MediaRef,
    MessageMeta,
    TraceId,
    TurnId,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-workspace")


class FakeClock:
    def __init__(self) -> None:
        self.current = NOW

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def _meta(event_id: str) -> MessageMeta:
    return MessageMeta(
        event_id=EventId(event_id),
        elfie_id=ELFIE_ID,
        source=ActorRef(actor_id=ActorId("producer"), source_kind="test"),
        occurred_at=NOW,
        received_at=NOW,
        trace_id=TraceId("trace-workspace"),
    )


def _event(index: int) -> PerceptionEvent:
    return PerceptionEvent(
        meta=_meta(f"event-{index}"),
        payload=PhysicalPayload(
            type="physical",
            body_id="body-1",
            modality=PhysicalModality.UTTERANCE,
            content=f"utterance {index}",
        ),
        salience=0.6,
    )


def _state(index: int, key: str) -> PerceptionStateUpdate:
    return PerceptionStateUpdate(
        meta=_meta(f"state-{index}"),
        state_key=key,
        revision=index,
        value=float(index),
    )


def _media(index: int, stream_id: str = "camera") -> PerceptionMediaSample:
    return PerceptionMediaSample(
        meta=_meta(f"media-{index}"),
        stream_id=stream_id,
        ordinal=index,
        captured_at=NOW,
        media=MediaRef(
            media_id=MediaId(f"media-{index}"),
            uri=f"memory://{stream_id}/{index}",
            mime_type="image/png",
        ),
    )


def test_ingest_sequence_is_unique_when_sixteen_producers_publish() -> None:
    # Given: sixteen producers released by one barrier.
    workspace = PerceptualWorkspace(
        elfie_id=ELFIE_ID,
        journal_capacity=1024,
        frame_event_capacity=1024,
    )
    barrier = Barrier(17)
    receipts = []
    receipts_lock = Lock()

    def publish_batch(producer: int) -> None:
        barrier.wait()
        batch = tuple(
            workspace.publish(_event(producer * 64 + offset)) for offset in range(64)
        )
        with receipts_lock:
            receipts.extend(batch)

    threads = tuple(Thread(target=publish_batch, args=(index,)) for index in range(16))

    # When: all producers publish concurrently.
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    # Then: all 1024 writes have a unique gap-free workspace sequence.
    sequences = sorted(receipt.ingest_seq for receipt in receipts)
    assert sequences == list(range(1, 1025))
    assert {receipt.disposition for receipt in receipts} == {IngestDisposition.ACCEPTED}
    assert workspace.metrics().reliable_event_count == 1024


def test_cutoff_release_replays_same_frame_and_commit_advances() -> None:
    # Given: three events before a cutoff and an active claim.
    workspace = PerceptualWorkspace(elfie_id=ELFIE_ID)
    for index in range(3):
        workspace.publish(_event(index))
    cutoff = workspace.metrics().latest_ingest_seq
    first = workspace.claim_frame(
        cutoff,
        turn_id=TurnId("turn-1"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )

    # When: later events arrive and the first claim is released.
    workspace.publish(_event(3))
    workspace.publish(_event(4))
    workspace.release(first.frame_id, TurnId("turn-1"), "model failed")
    replay_id = workspace.seal(reason=TriggerReason.MANUAL, captured_at=NOW)
    replay = workspace.claim(replay_id, TurnId("turn-2"))

    # Then: replay is identical; commit leaves later events for the next frame.
    assert replay == first
    workspace.commit(replay.frame_id, TurnId("turn-2"))
    second = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-3"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )
    assert tuple(event.meta.event_id for event in second.events) == (
        EventId("event-3"),
        EventId("event-4"),
    )
    assert second.frame_id != first.frame_id


def test_capacity_coalescing_and_duplicate_are_observable() -> None:
    # Given: deliberately tiny journal, state board, and media ring limits.
    workspace = PerceptualWorkspace(
        elfie_id=ELFIE_ID,
        journal_capacity=2,
        state_capacity=1,
        media_per_stream_capacity=2,
    )

    # When: each zone is driven beyond its configured capacity.
    first = workspace.publish(_event(1))
    workspace.publish(_event(2))
    duplicate = workspace.publish(_event(1))
    backpressured = workspace.publish(_event(3))
    workspace.publish(_state(1, "temperature"))
    state_coalesced = workspace.publish(_state(2, "temperature"))
    workspace.publish(_state(3, "humidity"))
    workspace.publish(_media(1))
    workspace.publish(_media(2))
    media_coalesced = workspace.publish(_media(3))
    frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-capacity"),
        reason=TriggerReason.CAPACITY,
        captured_at=NOW,
    )

    # Then: reliable data backpressures while bounded zones report loss.
    assert duplicate.disposition is IngestDisposition.DUPLICATE
    assert duplicate.ingest_seq == first.ingest_seq
    assert backpressured.disposition is IngestDisposition.BACKPRESSURED
    assert backpressured.retryable is True
    assert state_coalesced.disposition is IngestDisposition.COALESCED
    assert media_coalesced.disposition is IngestDisposition.COALESCED
    assert tuple(update.state_key for update in frame.state_updates) == ("humidity",)
    assert tuple(sample.ordinal for sample in frame.media_samples) == (2, 3)
    assert {summary.reason for summary in frame.dropped} == {
        "state_capacity",
        "media_capacity",
    }


def test_third_release_emits_one_reliable_failure_event_without_recursion() -> None:
    # Given: a claimed frame that repeatedly fails internal processing.
    workspace = PerceptualWorkspace(elfie_id=ELFIE_ID, journal_capacity=2)
    workspace.publish(_event(1))
    original = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-1"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )

    # When: the original frame is released three times.
    active = original
    for attempt in range(1, 4):
        turn_id = TurnId(f"turn-{attempt}")
        if attempt > 1:
            active = workspace.claim(active.frame_id, turn_id)
        workspace.release(active.frame_id, turn_id, f"failure {attempt}")

    # Then: typed failure evidence enters exactly one subsequent frame.
    failure_id = workspace.seal(reason=TriggerReason.MANUAL, captured_at=NOW)
    failure_frame = workspace.claim(failure_id, TurnId("failure-turn-1"))
    assert len(failure_frame.events) == 1
    assert isinstance(failure_frame.events[0], ProcessingFailureEvent)
    assert failure_frame.events[0].failed_frame_id == original.frame_id
    assert failure_frame.events[0].payload.signal is InternalSignal.PROCESSING_FAILURE
    assert len(workspace.dead_letters()) == 1
    restored = PerceptionFrame.model_validate_json(failure_frame.model_dump_json())
    assert isinstance(restored.events[0], ProcessingFailureEvent)
    assert restored.events[0].failed_frame_id == original.frame_id

    # When: processing the failure evidence itself also fails three times.
    for attempt in range(1, 4):
        turn_id = TurnId(f"failure-turn-{attempt}")
        if attempt > 1:
            failure_frame = workspace.claim(failure_frame.frame_id, turn_id)
        workspace.release(failure_frame.frame_id, turn_id, "failure evidence failed")

    # Then: it is committed without recursively generating another event.
    assert len(workspace.dead_letters()) == 1
    assert workspace.seal(reason=TriggerReason.MANUAL, captured_at=NOW) is None


def test_active_claim_is_exclusive_and_stop_wakes_waiter() -> None:
    # Given: one active claim and one deterministic condition waiter.
    clock = FakeClock()
    workspace = PerceptualWorkspace(elfie_id=ELFIE_ID, clock=clock.now)
    workspace.publish(_event(1))
    frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-1"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )
    with pytest.raises(ActiveClaimError):
        workspace.claim_frame(
            workspace.metrics().latest_ingest_seq,
            turn_id=TurnId("turn-2"),
            reason=TriggerReason.MANUAL,
            captured_at=NOW,
        )
    workspace.commit(frame.frame_id, TurnId("turn-1"))
    started = Event()
    results = []

    def wait() -> None:
        started.set()
        results.append(workspace.wait_for_change(clock.now() + timedelta(hours=1)))

    thread = Thread(target=wait)

    # When: stop is called after the waiter starts, without sleeping.
    thread.start()
    started.wait()
    workspace.stop()
    thread.join()

    # Then: the condition wakes deterministically with the stopped state.
    assert results == [WaitStatus.STOPPED]
    rejected = workspace.publish(_event(2))
    assert rejected.disposition is IngestDisposition.REJECTED
