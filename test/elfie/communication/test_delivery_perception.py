"""Delivery receipts entering the perceptual workspace."""

from __future__ import annotations

from datetime import datetime, timezone

from elfie.brain.workspace.contracts import (
    ExecutionStatus,
    IngestReceipt,
    SourceDomain,
    TriggerReason,
)
from elfie.brain.workspace.system import EventWorkspace
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    CommunicationPerceptionAdapter,
    DeliveryPerceptionCorrelation,
    DeliveryReceipt,
    DeliveryStatus,
    MessageDirection,
    TextPart,
)
from elfie.message_types import (
    ActorRef,
    ElfieId,
    IntentId,
    MessageMeta,
    PlanId,
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
        external_message_id=f"external-{index}",
        dedupe_key=f"webhook-{index}",
        parts=(TextPart(text=f"message body {index}"),),
    )


def outbound(index: int) -> CommunicationEnvelope:
    sender = ActorRef(actor_id=ELFIE_ID, source_kind="elfie")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=f"outbound-{index}",
            elfie_id=ELFIE_ID,
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id="trace-outbound",
        ),
        account_id="account-1",
        channel_id="test",
        conversation_id="conversation-1",
        sender=sender,
        recipients=(ActorRef(actor_id="owner-1", source_kind="platform"),),
        direction=MessageDirection.OUTBOUND,
        external_message_id=f"platform-outbound-{index}",
        dedupe_key=f"outbound-key-{index}",
        parts=(TextPart(text=f"reply {index}"),),
    )


def test_outbound_terminal_receipts_preserve_full_correlation() -> None:
    # Given: one connected channel returning three terminal delivery states.
    workspace = EventWorkspace(elfie_id=ELFIE_ID)
    hub = CommunicationHub(
        "elfie-1",
        perception_adapter=CommunicationPerceptionAdapter(workspace),
    )
    channel = ReceiptChannel()
    hub.register_channel(channel, connect=True)

    # When: sent, failed, and cancelled receipts are recorded by the outbox path.
    statuses = (
        DeliveryStatus.SENT,
        DeliveryStatus.FAILED,
        DeliveryStatus.CANCELLED,
    )
    for index, status in enumerate(statuses):
        channel.status = status
        hub.send_envelope(
            outbound(index),
            correlation=DeliveryPerceptionCorrelation(
                plan_id=PlanId("plan-1"),
                turn_id=TurnId("turn-1"),
                intent_id=IntentId(f"intent-{index}"),
            ),
        )
    frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-receipts"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )

    # Then: normalized execution events retain plan, intent, message, and external IDs.
    assert frame.source_domain is SourceDomain.COMMUNICATION
    assert tuple(event.payload.status for event in frame.events) == (
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.INTERRUPTED,
    )
    assert {event.payload.plan_id for event in frame.events} == {PlanId("plan-1")}
    assert tuple(event.payload.intent_id for event in frame.events) == tuple(
        IntentId(f"intent-{index}") for index in range(3)
    )
    assert tuple(event.meta.causation_id for event in frame.events) == tuple(
        f"outbound-{index}" for index in range(3)
    )
    assert tuple(event.meta.correlation_id for event in frame.events) == tuple(
        f"platform-outbound-{index}" for index in range(3)
    )


def test_hub_retry_perception_flattens_delivery_ingest_receipts() -> None:
    # Given: a full workspace retains one outbound delivery fact for retry.
    workspace = EventWorkspace(elfie_id=ELFIE_ID, journal_capacity=1)
    hub = CommunicationHub(
        "elfie-1",
        perception_adapter=CommunicationPerceptionAdapter(workspace),
    )
    channel = ReceiptChannel()
    hub.register_channel(channel, connect=True)
    hub.receive_envelope(inbound(0))
    hub.send_envelope(
        outbound(0),
        correlation=DeliveryPerceptionCorrelation(
            plan_id=PlanId("plan-retry"),
            turn_id=TurnId("turn-retry"),
            intent_id=IntentId("intent-retry"),
        ),
    )

    # When: capacity is released and the Hub retries every perception producer.
    frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-release"),
        reason=TriggerReason.CAPACITY,
        captured_at=NOW,
    )
    workspace.commit(frame.frame_id, TurnId("turn-release"))
    receipts = hub.retry_perception()

    # Then: callers receive one flat typed receipt sequence.
    assert len(receipts) == 1
    assert isinstance(receipts[0], IngestReceipt)
