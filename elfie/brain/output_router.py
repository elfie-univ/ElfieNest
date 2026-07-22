"""Atomic multi-intent output routing at the Brain root boundary."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Callable, Optional, Tuple
from uuid import uuid4

from elfie.brain.decision_types import CancelPolicy, DecisionIntent, DecisionPlan
from elfie.brain.output_execution_state import BatchRuntime, ExecutorRegistry
from elfie.brain.output_ports import EffectiveCapabilitiesSource, IntentExecutor
from elfie.brain.output_receipts import ExecutionReceiptPublisher
from elfie.brain.output_scheduler import OutputBatchScheduler
from elfie.brain.output_types import (
    BatchRejection,
    ExecutionBatch,
    ExecutionReceipt,
    ExecutorKind,
)
from elfie.brain.perception_types import ExecutionStatus
from elfie.brain.workspace_ports import PerceptionSink
from elfie.message_types import ElfieId, ErrorInfo, EventId, TurnId, UTCDateTime


class OutputRouter:
    """Validate complete plans, then schedule them outside Brain and Engine threads."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        capabilities: EffectiveCapabilitiesSource,
        perception_sink: PerceptionSink,
        body_executor: IntentExecutor,
        message_executor: IntentExecutor,
        internal_executor: IntentExecutor,
        clock: Callable[[], UTCDateTime],
        max_pending_batches: int = 8,
        max_intents_per_plan: int = 64,
        max_schedule_horizon_seconds: float = 60.0,
        max_workers: int = 4,
        completed_retention: int = 256,
    ) -> None:
        self._capabilities = capabilities
        self._clock = clock
        self._max_intents = max_intents_per_plan
        self._max_schedule_horizon = timedelta(
            seconds=max_schedule_horizon_seconds,
        )
        self._max_workers = max_workers
        self._completed_retention = completed_retention
        self._queue: Queue[BatchRuntime] = Queue(max_pending_batches)
        self._executors = ExecutorRegistry(
            body=body_executor,
            communication=message_executor,
            internal=internal_executor,
        )
        self._publisher = ExecutionReceiptPublisher(
            elfie_id=elfie_id,
            sink=perception_sink,
            clock=clock,
        )
        self._runtimes: OrderedDict[TurnId, BatchRuntime] = OrderedDict()
        self._plans: OrderedDict[str, DecisionPlan] = OrderedDict()
        self._thread: Optional[Thread] = None
        self._pool: Optional[ThreadPoolExecutor] = None
        self._lock = Lock()
        self._stop_requested = Event()
        self._accepting = False
        self._last_rejection: Optional[BatchRejection] = None
        self._evicted_completed_count = 0

    def start(self) -> None:
        """Start the bounded batch scheduler and target executor pool once."""
        with self._lock:
            if self._accepting:
                return
            self._queue = Queue(self._queue.maxsize)
            self._stop_requested.clear()
            self._pool = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="elfie-output",
            )
            self._accepting = True
            self._thread = Thread(
                target=self._run,
                name="elfie-output-router",
                daemon=False,
            )
            self._thread.start()

    def submit(self, plan: DecisionPlan) -> ExecutionBatch | BatchRejection:
        """Atomically validate and enqueue a plan without executing inline."""
        with self._lock:
            existing = self._plans.get(str(plan.plan_id))
            if existing is not None:
                runtime = self._runtimes[existing.turn_id]
                if existing == plan:
                    return runtime.batch
                return self._reject(plan, "idempotency_conflict", "plan ID was reused")
            if not self._accepting:
                return self._reject(plan, "router_not_running", "output router is stopped")
            error = self._validate(plan)
            if error is not None:
                return self._reject(plan, error.code, error.message)
            if self._queue.full():
                return self._reject(plan, "output_backpressure", "output queue is full")
            batch = ExecutionBatch(
                batch_id=EventId(f"execution_batch_{uuid4().hex}"),
                plan_id=plan.plan_id,
                turn_id=plan.turn_id,
                accepted_at=self._clock(),
                intent_ids=tuple(intent.intent_id for intent in plan.intents),
            )
            runtime = BatchRuntime(batch, plan)
            self._plans[str(plan.plan_id)] = plan
            self._runtimes[plan.turn_id] = runtime
            self._trim_completed_locked()
            for intent in plan.intents:
                kind, _executor = self._executors.for_intent(intent)
                self._emit(plan, intent, kind, ExecutionStatus.ACCEPTED, None)
            self._queue.put_nowait(runtime)
        return batch

    def accept(self, plan: DecisionPlan) -> bool:
        """DecisionPlanSink compatibility used by BrainCoordinator."""
        return isinstance(self.submit(plan), ExecutionBatch)

    def cancel_stale(self, turn_id: TurnId, reason: str) -> None:
        self.cancel_for_stale_turn(turn_id, reason)

    def cancel_for_stale_turn(self, turn_id: TurnId, reason: str) -> None:
        """Cancel pending work and interrupt only explicitly interruptible work."""
        with self._lock:
            runtime = self._runtimes.get(turn_id)
        if runtime is None:
            return
        for intent in runtime.cancel(reason):
            if intent.cancel_policy is CancelPolicy.ALWAYS:
                _kind, executor = self._executors.for_intent(intent)
                executor.interrupt(turn_id, intent.intent_id, reason)

    def wait_for_turn(self, turn_id: TurnId, *, timeout: float) -> None:
        with self._lock:
            runtime = self._runtimes.get(turn_id)
        if runtime is None or not runtime.done.wait(timeout):
            raise TimeoutError(f"output turn did not complete: {turn_id}")

    def receipts(self, turn_id: TurnId) -> Tuple[ExecutionReceipt, ...]:
        return self._publisher.receipts_for(str(turn_id))

    def retry_receipts(self) -> Tuple[EventId, ...]:
        return self._publisher.retry_pending()

    @property
    def evicted_completed_count(self) -> int:
        with self._lock:
            return self._evicted_completed_count

    @property
    def last_rejection(self) -> Optional[BatchRejection]:
        with self._lock:
            return self._last_rejection

    def stop(self) -> None:
        with self._lock:
            if not self._accepting:
                return
            self._accepting = False
            self._stop_requested.set()

    def join(self) -> None:
        with self._lock:
            thread = self._thread
            pool = self._pool
        if thread is not None:
            thread.join()
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        with self._lock:
            self._thread = None
            self._pool = None

    def _run(self) -> None:
        pool = self._pool
        if pool is None:
            return
        scheduler = OutputBatchScheduler(
            pool=pool,
            executors=self._executors,
            emit=self._emit,
            capability_check=self._validate_intent,
            wait_until=self._wait_until,
        )
        while True:
            try:
                runtime = self._queue.get(timeout=0.05)
            except Empty:
                if self._stop_requested.is_set():
                    return
                continue
            scheduler.execute(runtime)
            if self._stop_requested.is_set() and self._queue.empty():
                return

    def _validate(self, plan: DecisionPlan) -> Optional[ErrorInfo]:
        from elfie.brain.output_validation import validate_plan_for_execution

        return validate_plan_for_execution(
            plan,
            self._capabilities.current(),
            now=self._clock(),
            max_intents=self._max_intents,
            max_schedule_horizon=self._max_schedule_horizon,
        )

    def _validate_intent(
        self,
        plan: DecisionPlan,
        _intent: DecisionIntent,
    ) -> Optional[ErrorInfo]:
        return self._validate(plan)

    def _wait_until(self, target: UTCDateTime, cancelled: Event) -> bool:
        while target > self._clock():
            remaining = (target - self._clock()).total_seconds()
            if cancelled.wait(remaining):
                return False
        return True

    def _emit(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
        kind: ExecutorKind,
        status: ExecutionStatus,
        error: Optional[ErrorInfo],
    ) -> None:
        self._publisher.emit(
            plan=plan,
            intent=intent,
            executor=kind,
            status=status,
            error=error,
        )

    def _reject(self, plan: DecisionPlan, code: str, message: str) -> BatchRejection:
        rejection = BatchRejection(
            plan_id=plan.plan_id,
            turn_id=plan.turn_id,
            rejected_at=self._clock(),
            error=ErrorInfo(code=code, message=message),
        )
        self._last_rejection = rejection
        return rejection

    def _trim_completed_locked(self) -> None:
        completed = [
            turn_id
            for turn_id, runtime in self._runtimes.items()
            if runtime.done.is_set()
        ]
        overflow = len(completed) - self._completed_retention
        for turn_id in completed[: max(0, overflow)]:
            runtime = self._runtimes.pop(turn_id)
            self._plans.pop(str(runtime.plan.plan_id), None)
            self._evicted_completed_count += 1


__all__ = ("OutputRouter",)
