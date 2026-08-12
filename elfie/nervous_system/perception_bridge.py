"""Backpressure-aware Body-to-Brain adapter owned by NervousSystem."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Iterable, List, Optional, Tuple

from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    EmergencyStopCommand,
    TactileImpact,
)
from elfie.body.port import BodyPort
from elfie.brain.perception_types import (
    IngestDisposition,
    IngestReceipt,
    PerceptionEvent,
    PerceptionWrite,
)
from elfie.brain.workspace_ports import PerceptionSink
from elfie.message_types import ElfieId
from elfie.nervous_system.perception_normalizer import BodyPerceptionNormalizer
from elfie.nervous_system.perception_reflex import (
    DANGER_FORCE_NEWTONS,
    BodyReflexController,
)


class BodyPerceptionBridge:
    """Mutable adapter whose pending queue preserves reliable input order."""

    def __init__(
        self,
        *,
        sink: PerceptionSink,
        elfie_id: ElfieId,
        normalizer: BodyPerceptionNormalizer,
        body_port: Optional[BodyPort] = None,
        body_generation: int | None = None,
        max_pending_events: int = 512,
    ) -> None:
        self._sink = sink
        self._elfie_id = elfie_id
        self._normalizer = normalizer
        self._pending: Deque[PerceptionEvent] = deque()
        self._max_pending_events = max_pending_events
        self._dropped_pending_count = 0
        self._closed = False
        self._filtered_count = 0
        self._state_lock = Lock()
        self._pending_lock = Lock()
        self._draining = False
        # Bare NervousSystem tests may use this adapter without a bound Body;
        # Elfie explicitly binds (including ``None``) and therefore enables
        # the authority check below.
        self._enforce_body_binding = body_port is not None
        self._reflex = BodyReflexController(
            elfie_id=elfie_id,
            body_port=body_port,
            body_generation=body_generation,
        )
        self._body_id = (
            BodyId(str(body_port.body_id)) if body_port is not None else None
        )
        self._body_generation = (
            (body_generation or 1) if body_port is not None else None
        )

    @property
    def pending_count(self) -> int:
        with self._pending_lock:
            return len(self._pending)

    @property
    def filtered_count(self) -> int:
        with self._state_lock:
            return self._filtered_count

    @property
    def dropped_pending_count(self) -> int:
        with self._pending_lock:
            return self._dropped_pending_count

    @property
    def urgent_revision(self) -> int:
        return self._reflex.urgent_revision

    @property
    def last_reflex_command(self) -> Optional[EmergencyStopCommand]:
        return self._reflex.last_command

    def bind_body_port(
        self,
        body_port: Optional[BodyPort],
        *,
        body_generation: int | None = None,
    ) -> None:
        """Update the reflex target after a Body lifecycle transition."""
        self._reflex.bind_body_port(body_port, body_generation=body_generation)
        with self._state_lock:
            self._enforce_body_binding = True
            self._body_id = (
                BodyId(str(body_port.body_id)) if body_port is not None else None
            )
            self._body_generation = (
                (body_generation or 1) if body_port is not None else None
            )

    def receive(self, events: Iterable[BodySensorEvent]) -> Tuple[IngestReceipt, ...]:
        receipts: Tuple[IngestReceipt, ...] = ()
        for event in events:
            receipts += self.receive_body_event(event)
        return receipts

    def receive_body_event(
        self,
        event: BodySensorEvent,
    ) -> Tuple[IngestReceipt, ...]:
        with self._pending_lock:
            if self._closed:
                return (
                    IngestReceipt(
                        event_id=event.event_id,
                        disposition=IngestDisposition.REJECTED,
                        ingest_seq=None,
                        retryable=False,
                        reason="body_perception_closed",
                    ),
                )
        with self._state_lock:
            expected_body_id = self._body_id
            expected_generation = self._body_generation
        if self._enforce_body_binding and expected_body_id is None:
            return (
                IngestReceipt(
                    event_id=event.event_id,
                    disposition=IngestDisposition.REJECTED,
                    ingest_seq=None,
                    retryable=False,
                    reason="no_current_body",
                ),
            )
        if expected_body_id is not None and event.body_id != expected_body_id:
            return (
                IngestReceipt(
                    event_id=event.event_id,
                    disposition=IngestDisposition.REJECTED,
                    ingest_seq=None,
                    retryable=False,
                    reason="foreign_body",
                ),
            )
        if expected_generation is not None and event.body_generation != expected_generation:
            return (
                IngestReceipt(
                    event_id=event.event_id,
                    disposition=IngestDisposition.REJECTED,
                    ingest_seq=None,
                    retryable=False,
                    reason="stale_body_generation",
                ),
            )
        with self._state_lock:
            writes = self._normalizer.normalize(event)
            if not writes:
                self._filtered_count += 1
                return ()
            payload = event.payload
            reflex_required = False
            if isinstance(payload, TactileImpact) and (
                (payload.force_newtons or 0.0) >= DANGER_FORCE_NEWTONS
            ):
                reflex_required = True
        if reflex_required and isinstance(payload, TactileImpact):
            writes += self._reflex.handle(event, payload)
        return self._publish(writes)

    def retry_pending(self) -> Tuple[IngestReceipt, ...]:
        receipts: List[IngestReceipt] = []
        with self._pending_lock:
            if self._draining:
                return ()
            self._draining = True
        try:
            while True:
                with self._pending_lock:
                    if not self._pending:
                        break
                    event = self._pending[0]
                receipt = self._sink.publish(event)
                receipts.append(receipt)
                if receipt.disposition not in {
                    IngestDisposition.ACCEPTED,
                    IngestDisposition.DUPLICATE,
                }:
                    break
                with self._pending_lock:
                    if self._pending and self._pending[0] is event:
                        self._pending.popleft()
        finally:
            with self._pending_lock:
                self._draining = False
        return tuple(receipts)

    def _publish(
        self,
        writes: Tuple[PerceptionWrite, ...],
    ) -> Tuple[IngestReceipt, ...]:
        receipts: Tuple[IngestReceipt, ...] = ()
        for write in writes:
            if isinstance(write, PerceptionEvent):
                with self._pending_lock:
                    if len(self._pending) >= self._max_pending_events:
                        self._pending.popleft()
                        self._dropped_pending_count += 1
                    self._pending.append(write)
                receipts += self.retry_pending()
            else:
                receipts += (self._sink.publish(write),)
        return receipts

    def close(self) -> None:
        """Reject future Body input and release pending reliable events."""
        with self._pending_lock:
            self._closed = True
            self._pending.clear()


__all__ = ("BodyPerceptionBridge",)
