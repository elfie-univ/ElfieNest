"""Concurrency and reentrancy tests for the Body perception bridge."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from elfie.body.contracts import UtteranceFinal
from elfie.brain.perception_types import (
    IngestDisposition,
    IngestReceipt,
    PerceptionWrite,
)
from elfie.message_types import EventId
from elfie.nervous_system import NervousSystem
from test.elfie.nervous_system.perception_bridge_fixtures import (
    ELFIE_ID,
    OWNER,
    ROOM,
    body_event,
)


def test_concurrent_body_producers_publish_each_reliable_event_once() -> None:
    # Given: two producers reach a sink publication at the same time.
    class CoordinatedSink:
        def __init__(self) -> None:
            self.lock = Lock()
            self.event_ids: list[EventId] = []
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
        body_event(
            "concurrent-1",
            ROOM,
            UtteranceFinal(kind="utterance_final", text="第一条"),
        ),
        body_event(
            "concurrent-2",
            OWNER,
            UtteranceFinal(kind="utterance_final", text="第二条"),
        ),
    )

    # When: both producers publish concurrently.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(
            pool.submit(nervous_system.receive_body_event, event) for event in events
        )
        tuple(future.result() for future in futures)

    # Then: neither event is duplicated or removed by the other producer.
    assert sorted(sink.event_ids) == [
        EventId("concurrent-1"),
        EventId("concurrent-2"),
    ]
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
        body_event(
            "reentrant-event",
            ROOM,
            UtteranceFinal(kind="utterance_final", text="可重入"),
        )
    )

    # Then: the nested retry yields to the active owner and the event commits.
    assert sink.nested_retry_count == 0
    assert nervous_system.pending_count == 0
