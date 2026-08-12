"""Reliable execution-receipt publication into the perceptual workspace."""

from __future__ import annotations

from collections import OrderedDict, deque
from threading import Lock
from typing import Callable, Tuple
from uuid import uuid4

from elfie.brain.reasoning.decision_types import DecisionIntent, DecisionPlan
from elfie.brain.reasoning.execution_types import ExecutionReceipt, ExecutorKind
from elfie.brain.workspace.contracts import (
    ExecutionPayload,
    ExecutionStatus,
    IngestDisposition,
    PerceptionEvent,
)
from elfie.brain.workspace.ports import PerceptionSink
from elfie.message_types import (
    ActorId,
    ActorRef,
    CorrelationId,
    ElfieId,
    ErrorInfo,
    EventId,
    MessageMeta,
    Priority,
    TraceId,
    UTCDateTime,
)


class ReceiptBacklogFullError(RuntimeError):
    """The bounded reliable receipt backlog cannot accept another event."""


class ExecutionReceiptPublisher:
    """Publish receipts once and retain backpressured events for explicit retry."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        sink: PerceptionSink,
        clock: Callable[[], UTCDateTime],
        max_pending: int = 1024,
        max_receipts: int = 2048,
    ) -> None:
        self._elfie_id = elfie_id
        self._sink = sink
        self._clock = clock
        self._max_pending = max_pending
        self._max_receipts = max_receipts
        self._pending: OrderedDict[EventId, PerceptionEvent] = OrderedDict()
        self._receipts: deque[ExecutionReceipt] = deque()
        self._evicted_receipt_count = 0
        self._dropped_pending_count = 0
        self._lock = Lock()

    def emit(
        self,
        *,
        plan: DecisionPlan,
        intent: DecisionIntent,
        executor: ExecutorKind,
        status: ExecutionStatus,
        error: ErrorInfo | None = None,
    ) -> ExecutionReceipt:
        """Create one transition and publish its normalized perception event."""
        receipt = ExecutionReceipt(
            receipt_id=EventId(f"execution_receipt_{uuid4().hex}"),
            plan_id=plan.plan_id,
            turn_id=plan.turn_id,
            intent_id=intent.intent_id,
            executor=executor,
            status=status,
            occurred_at=self._clock(),
            error=error,
        )
        event = self._event(plan, intent, receipt)
        with self._lock:
            if len(self._receipts) >= self._max_receipts:
                self._receipts.popleft()
                self._evicted_receipt_count += 1
            self._receipts.append(receipt)
        ingest = self._sink.publish(event)
        if ingest.disposition is IngestDisposition.BACKPRESSURED:
            with self._lock:
                if len(self._pending) >= self._max_pending:
                    self._pending.popitem(last=False)
                    self._dropped_pending_count += 1
                self._pending[receipt.receipt_id] = event
        return receipt

    def retry_pending(self) -> Tuple[EventId, ...]:
        """Retry retained receipts in source order until backpressure recurs."""
        completed: list[EventId] = []
        with self._lock:
            pending = tuple(self._pending.items())
        for receipt_id, event in pending:
            ingest = self._sink.publish(event)
            if ingest.disposition is IngestDisposition.BACKPRESSURED:
                break
            with self._lock:
                self._pending.pop(receipt_id, None)
            completed.append(receipt_id)
        return tuple(completed)

    def receipts_for(self, turn_id: str) -> Tuple[ExecutionReceipt, ...]:
        with self._lock:
            return tuple(
                receipt for receipt in self._receipts if str(receipt.turn_id) == turn_id
            )

    @property
    def evicted_receipt_count(self) -> int:
        with self._lock:
            return self._evicted_receipt_count

    @property
    def dropped_pending_count(self) -> int:
        with self._lock:
            return self._dropped_pending_count

    def _event(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
        receipt: ExecutionReceipt,
    ) -> PerceptionEvent:
        source = ActorRef(
            actor_id=ActorId(f"{self._elfie_id}:output-router"),
            source_kind="internal",
        )
        return PerceptionEvent(
            meta=MessageMeta(
                event_id=receipt.receipt_id,
                elfie_id=self._elfie_id,
                source=source,
                occurred_at=receipt.occurred_at,
                received_at=receipt.occurred_at,
                trace_id=TraceId(f"execution:{plan.turn_id}"),
                causation_id=intent.cause_event_ids[0],
                correlation_id=CorrelationId(str(plan.plan_id)),
                priority=(
                    Priority.HIGH if receipt.error is not None else Priority.NORMAL
                ),
            ),
            payload=ExecutionPayload(
                type="execution",
                receipt_id=receipt.receipt_id,
                plan_id=receipt.plan_id,
                turn_id=receipt.turn_id,
                intent_id=receipt.intent_id,
                executor=receipt.executor.value,
                status=receipt.status,
                error=receipt.error,
            ),
            salience=0.8 if receipt.error is not None else 0.4,
        )


__all__ = ("ExecutionReceiptPublisher", "ReceiptBacklogFullError")
