"""Communication envelopes and receipts entering the perceptual workspace."""

from __future__ import annotations

from datetime import datetime, timezone

from elfie.brain.perception_types import (
    IngestDisposition,
    IngestReceipt,
    PerceptionWrite,
    SocialPayload,
    TriggerReason,
)
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    CommunicationPerceptionAdapter,
    DeliveryReceipt,
    DeliveryStatus,
    InboundDispositionStatus,
    MessageDirection,
    TextPart,
)
from elfie.message_types import (
    ActorRef,
    ElfieId,
    MessageMeta,
    TurnId,
)

NOW = datetime(2026, 7, 21, 9, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-1")


class ReceiptChannel:
    channel_id = "test"

    def __init__(self) -> None:
        self._connected = False
        self.status = DeliveryStatus.SENT

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        failed = self.status in {DeliveryStatus.FAILED, DeliveryStatus.CANCELLED}
        return DeliveryReceipt.for_envelope(
            envelope,
            status=self.status,
            error_code="delivery_terminal" if failed else None,
        )


def inbound(index: int) -> CommunicationEnvelope:
    sender = ActorRef(actor_id=f"sender-{index}", source_kind="platform")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=f"message-{index}",
            elfie_id=ELFIE_ID,
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id="trace-burst",
        ),
        account_id="account-1",
        channel_id="test",
        conversation_id="conversation-1",
        sender=sender,
        recipients=(ActorRef(actor_id=ELFIE_ID, source_kind="elfie"),),
        direction=MessageDirection.INBOUND,
        reply_to=f"parent-{index}",
        external_message_id=f"external-{index}",
        dedupe_key=f"webhook-{index}",
        sequence_id="burst-1",
        ordinal=index,
        parts=(TextPart(text=f"message body {index}"),),
    )


def test_five_message_burst_remains_five_ordered_social_events() -> None:
    # Given: one Hub connected to a real workspace and one conversation burst.
    workspace = PerceptualWorkspace(elfie_id=ELFIE_ID)
    hub = CommunicationHub(
        "elfie-1",
        perception_adapter=CommunicationPerceptionAdapter(workspace),
    )
    hub.register_channel(ReceiptChannel())

    # When: five complete envelopes arrive before the frame is sealed.
    dispositions = tuple(hub.receive_envelope(inbound(index)) for index in range(5))
    frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-burst"),
        reason=TriggerReason.CONVERSATION_QUIET,
        captured_at=NOW,
    )

    # Then: every message remains one ordered fact with its own identity.
    assert all(
        disposition.status is InboundDispositionStatus.ACCEPTED
        for disposition in dispositions
    )
    assert hub.inbox.pending_count == 0
    assert tuple(event.meta.event_id for event in frame.events) == tuple(
        f"message-{index}" for index in range(5)
    )
    payloads = tuple(event.payload for event in frame.events)
    assert all(isinstance(payload, SocialPayload) for payload in payloads)
    assert tuple(payload.sender.actor_id for payload in payloads) == tuple(
        f"sender-{index}" for index in range(5)
    )
    assert tuple(payload.reply_to_event_id for payload in payloads) == tuple(
        f"parent-{index}" for index in range(5)
    )


def test_backpressured_inbound_retries_the_same_envelope_once() -> None:
    # Given: one workspace slot already occupied by the first message.
    workspace = PerceptualWorkspace(elfie_id=ELFIE_ID, journal_capacity=1)
    hub = CommunicationHub(
        "elfie-1",
        perception_adapter=CommunicationPerceptionAdapter(workspace),
    )
    hub.register_channel(ReceiptChannel())
    first = inbound(1)
    backpressured = inbound(2)
    hub.receive_envelope(first)

    # When: a second message backpressures and its webhook is replayed.
    admitted = hub.receive_envelope(backpressured)
    duplicate = hub.receive_envelope(backpressured)

    # Then: the exact envelope remains pending without a second publication.
    assert admitted.status is InboundDispositionStatus.ACCEPTED
    assert duplicate.status is InboundDispositionStatus.DUPLICATE
    assert hub.inbox.pending_count == 1
    assert hub.perception_adapter.pending_inbound == (backpressured,)

    # When: committing the first frame releases capacity and retry runs.
    first_frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-first"),
        reason=TriggerReason.CAPACITY,
        captured_at=NOW,
    )
    workspace.commit(first_frame.frame_id, TurnId("turn-first"))
    receipts = hub.retry_perception()
    second_frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-second"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )

    # Then: retry publishes that event once and completes cognitive delivery.
    assert len(receipts) == 1
    assert hub.inbox.pending_count == 0
    assert hub.perception_adapter.pending_inbound == ()
    assert tuple(event.meta.event_id for event in second_frame.events) == (
        backpressured.meta.event_id,
    )


def test_adapter_does_not_hold_internal_lock_during_sink_publish() -> None:
    # Given: a sink inspects adapter pending state from inside publish.
    class ReentrantSink:
        adapter: CommunicationPerceptionAdapter | None = None
        observed_pending = ()

        def publish(self, write: PerceptionWrite) -> IngestReceipt:
            adapter = self.adapter
            assert adapter is not None
            self.observed_pending = adapter.pending_inbound
            return IngestReceipt(
                event_id=write.meta.event_id,
                disposition=IngestDisposition.ACCEPTED,
                ingest_seq=1,
                retryable=False,
                reason=None,
            )

    sink = ReentrantSink()
    adapter = CommunicationPerceptionAdapter(sink)
    sink.adapter = adapter
    envelope = inbound(9)

    # When: the adapter publishes one inbound envelope.
    attempt = adapter.publish_inbound(envelope)

    # Then: callback access completes and observes the queued envelope.
    assert attempt.completed is True
    assert sink.observed_pending == (envelope,)
    assert adapter.pending_inbound == ()
