"""Bounded communication buffers for long-running Elfie processes."""

from __future__ import annotations

from threading import Event, Thread

from elfie.brain.workspace.contracts import (
    IngestDisposition,
    IngestReceipt,
    PerceptionWrite,
)
from elfie.communication import (
    CommunicationHub,
    CommunicationPerceptionAdapter,
    InboundDispositionStatus,
)
from elfie.communication.inbox import CommunicationInbox
from test.elfie.communication.test_perception_adapter import (
    ReceiptChannel,
    inbound,
)


def test_inbox_retention_windows_evict_old_history_and_dedupe_identity() -> None:
    # Given: an inbox with one retained history item and one dedupe identity.
    inbox = CommunicationInbox(
        max_pending=4,
        history_capacity=1,
        dedupe_capacity=1,
    )
    first = inbound(1)
    second = inbound(2)

    # When: two envelopes are admitted.
    assert inbox.claim_identity(first) is True
    inbox.receive(first)
    assert inbox.claim_identity(second) is True
    inbox.receive(second)

    # Then: pending remains bounded by work, while history/dedupe windows evict.
    metrics = inbox.metrics()
    assert inbox.history == [second]
    assert metrics.pending_count == 2
    assert metrics.history_count == 1
    assert metrics.evicted_history_count == 1
    assert metrics.evicted_identity_count >= 1


def test_closed_hub_rejects_inbound_without_retaining_history() -> None:
    # Given: a hub has been closed during Elfie runtime shutdown.
    hub = CommunicationHub("elfie-1")
    hub.register_channel(ReceiptChannel())
    hub.close()

    # When: a platform retries an inbound message after shutdown.
    disposition = hub.receive_envelope(inbound(1))

    # Then: the input is rejected and no message accumulates.
    assert disposition.status is InboundDispositionStatus.REJECTED
    assert disposition.error is not None
    assert disposition.error.code == "communication_closed"
    assert hub.inbox.metrics().pending_count == 0
    assert hub.inbox.metrics().history_count == 0


def test_closed_adapter_rejects_publication_without_retry_backlog() -> None:
    # Given: a communication perception adapter has been closed.
    class RejectingSink:
        def publish(self, write: PerceptionWrite) -> IngestReceipt:
            raise AssertionError(f"sink should not be called: {write}")

    adapter = CommunicationPerceptionAdapter(RejectingSink())
    adapter.close()

    # When: an already parsed envelope is published after shutdown.
    attempt = adapter.publish_inbound(inbound(1))

    # Then: no retry backlog is retained.
    assert attempt.receipt.disposition is IngestDisposition.REJECTED
    assert adapter.pending_inbound == ()


def test_hub_close_waits_for_inflight_receive_publication() -> None:
    # Given: a hub whose workspace sink asks shutdown to race during publish.
    close_started = Event()
    close_returned = Event()

    class ClosingSink:
        hub: CommunicationHub | None = None

        def publish(self, write: PerceptionWrite) -> IngestReceipt:
            hub = self.hub
            assert hub is not None

            def request_close() -> None:
                close_started.set()
                hub.close()
                close_returned.set()

            Thread(target=request_close).start()
            assert close_started.wait(1)
            assert close_returned.is_set() is False
            return IngestReceipt(
                event_id=write.meta.event_id,
                disposition=IngestDisposition.ACCEPTED,
                ingest_seq=1,
                retryable=False,
                reason=None,
            )

    sink = ClosingSink()
    hub = CommunicationHub(
        "elfie-1",
        perception_adapter=CommunicationPerceptionAdapter(sink),
    )
    sink.hub = hub
    hub.register_channel(ReceiptChannel())

    # When: close races after inbox admission but before publish returns.
    disposition = hub.receive_envelope(inbound(1))

    # Then: the receive completes publication before close clears boundaries.
    assert disposition.status is InboundDispositionStatus.ACCEPTED
    assert close_returned.wait(1)
    assert hub.inbox.metrics().closed is True
    assert hub.inbox.metrics().pending_count == 0
