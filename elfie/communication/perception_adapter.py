"""Typed Communication producer adapter for the Brain perception sink."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import List, NamedTuple, Tuple

from elfie.brain.perception_types import (
    IngestDisposition,
    IngestReceipt,
    PerceptionEvent,
)
from elfie.brain.workspace_ports import PerceptionSink
from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    MessageDirection,
)
from elfie.communication.perception_conversion import (
    build_execution_event,
    build_social_event,
    completes_cognitive_delivery,
)
from elfie.message_types import EventId, IntentId, PlanId, TurnId


class DeliveryPerceptionCorrelation(NamedTuple):
    """Decision identity supplied by the output router for one message."""

    plan_id: PlanId
    turn_id: TurnId
    intent_id: IntentId


class InboundPerceptionAttempt(NamedTuple):
    """One retryable inbound publication and its workspace disposition."""

    envelope: CommunicationEnvelope
    receipt: IngestReceipt

    @property
    def completed(self) -> bool:
        """Whether the workspace retained this cognitive delivery."""
        return completes_cognitive_delivery(self.receipt.disposition)


class AdapterDirectionError(ValueError):
    """An envelope crossed the wrong side of the perception adapter."""

    __slots__ = ("actual", "expected")

    def __init__(
        self,
        expected: MessageDirection,
        actual: MessageDirection,
    ) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"expected {self.expected.value} envelope, got {self.actual.value}"


class CommunicationPerceptionAdapter:
    """Publish communication facts without exposing workspace internals."""

    def __init__(self, sink: PerceptionSink) -> None:
        self._sink = sink
        self._pending_inbound: OrderedDict[EventId, CommunicationEnvelope] = (
            OrderedDict()
        )
        self._pending_delivery: OrderedDict[EventId, PerceptionEvent] = OrderedDict()
        self._lock = Lock()

    def publish_inbound(
        self,
        envelope: CommunicationEnvelope,
    ) -> InboundPerceptionAttempt:
        """Publish one complete inbound envelope or retain it for retry."""
        self._require_direction(envelope, MessageDirection.INBOUND)
        with self._lock:
            self._pending_inbound[envelope.meta.event_id] = envelope
        receipt = self._sink.publish(build_social_event(envelope))
        with self._lock:
            if completes_cognitive_delivery(receipt.disposition):
                self._pending_inbound.pop(envelope.meta.event_id, None)
        return InboundPerceptionAttempt(envelope=envelope, receipt=receipt)

    def publish_delivery(
        self,
        envelope: CommunicationEnvelope,
        receipt: DeliveryReceipt,
        correlation: DeliveryPerceptionCorrelation,
    ) -> IngestReceipt:
        """Publish one delivery receipt or retain its normalized event."""
        self._require_direction(envelope, MessageDirection.OUTBOUND)
        event = build_execution_event(envelope, receipt, correlation)
        with self._lock:
            self._pending_delivery[event.meta.event_id] = event
        ingest = self._sink.publish(event)
        with self._lock:
            if completes_cognitive_delivery(ingest.disposition):
                self._pending_delivery.pop(event.meta.event_id, None)
        return ingest

    def retry_inbound(self) -> Tuple[InboundPerceptionAttempt, ...]:
        """Retry pending inbound envelopes once in original arrival order."""
        attempts: List[InboundPerceptionAttempt] = []
        with self._lock:
            pending = tuple(self._pending_inbound.items())
        for event_id, envelope in pending:
            receipt = self._sink.publish(build_social_event(envelope))
            attempts.append(InboundPerceptionAttempt(envelope, receipt))
            with self._lock:
                if completes_cognitive_delivery(receipt.disposition):
                    self._pending_inbound.pop(event_id, None)
            if receipt.disposition is IngestDisposition.BACKPRESSURED:
                break
        return tuple(attempts)

    def retry_delivery(self) -> Tuple[IngestReceipt, ...]:
        """Retry normalized delivery events once in receipt order."""
        receipts: List[IngestReceipt] = []
        with self._lock:
            pending = tuple(self._pending_delivery.items())
        for event_id, event in pending:
            receipt = self._sink.publish(event)
            receipts.append(receipt)
            with self._lock:
                if completes_cognitive_delivery(receipt.disposition):
                    self._pending_delivery.pop(event_id, None)
            if receipt.disposition is IngestDisposition.BACKPRESSURED:
                break
        return tuple(receipts)

    @property
    def pending_inbound(self) -> Tuple[CommunicationEnvelope, ...]:
        with self._lock:
            return tuple(self._pending_inbound.values())

    @property
    def pending_delivery_count(self) -> int:
        with self._lock:
            return len(self._pending_delivery)

    @staticmethod
    def _require_direction(
        envelope: CommunicationEnvelope,
        expected: MessageDirection,
    ) -> None:
        if envelope.direction is not expected:
            raise AdapterDirectionError(expected=expected, actual=envelope.direction)

__all__ = (
    "AdapterDirectionError",
    "CommunicationPerceptionAdapter",
    "DeliveryPerceptionCorrelation",
    "InboundPerceptionAttempt",
)
