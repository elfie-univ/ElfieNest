"""Atomic multi-intent output routing at the Brain root boundary."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Callable, Optional, Tuple
from uuid import uuid4

from elfie.brain.journal import BrainJournal
from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionIntent,
    DecisionPlan,
    NoOpIntent,
    TurnDecision,
)
from elfie.brain.reasoning.execution_ports import (
    EffectiveCapabilitiesSource,
    IntentExecutor,
)
from elfie.brain.reasoning.execution_receipts import ExecutionReceiptPublisher
from elfie.brain.reasoning.execution_scheduler import OutputBatchScheduler
from elfie.brain.reasoning.execution_state import BatchRuntime, ExecutorRegistry
from elfie.brain.reasoning.execution_types import (
    BatchRejection,
    ExecutionBatch,
    ExecutionReceipt,
    ExecutorKind,
)
from elfie.brain.workspace.contracts import (
    EmbodiedScope,
    ExecutionStatus,
    InteractionScope,
)
from elfie.brain.workspace.ports import PerceptionSink
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
        activity_executor: IntentExecutor | None = None,
        clock: Callable[[], UTCDateTime],
        max_pending_batches: int = 8,
        max_intents_per_plan: int = 64,
        max_schedule_horizon_seconds: float = 60.0,
        max_workers: int = 4,
        completed_retention: int = 256,
        receipt_handler: Callable[
            [DecisionPlan, DecisionIntent, ExecutionReceipt], None
        ]
        | None = None,
        decision_handler: Callable[[TurnDecision], None] | None = None,
        journal: BrainJournal | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._body_executor = body_executor
        self._clock = clock
        self._max_intents = max_intents_per_plan
        self._max_schedule_horizon = timedelta(
            seconds=max_schedule_horizon_seconds,
        )
        self._max_workers = max_workers
        self._completed_retention = completed_retention
        self._receipt_handler = receipt_handler
        self._decision_handler = decision_handler
        self._journal = journal
        self._queue: Queue[BatchRuntime] = Queue(max_pending_batches)
        self._executors = ExecutorRegistry(
            body=body_executor,
            communication=message_executor,
            internal=internal_executor,
            activity=activity_executor or _closed_activity_executor(),
        )
        self._publisher = ExecutionReceiptPublisher(
            elfie_id=elfie_id,
            sink=perception_sink,
            clock=clock,
        )
        self._runtimes: OrderedDict[TurnId, BatchRuntime] = OrderedDict()
        self._decisions: OrderedDict[str, TurnDecision] = OrderedDict()
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

    def submit(self, decision: TurnDecision) -> ExecutionBatch | BatchRejection:
        """Atomically validate and enqueue one governed turn decision."""
        plan = decision.plan
        with self._lock:
            existing = self._decisions.get(str(plan.plan_id))
            if existing is not None:
                runtime = self._runtimes[existing.plan.turn_id]
                if existing == decision:
                    return runtime.batch
                return self._reject(
                    decision, "idempotency_conflict", "plan ID was reused"
                )
            if not self._accepting:
                return self._reject(
                    decision, "router_not_running", "output router is stopped"
                )
            error = self._validate(decision)
            if error is not None:
                return self._reject(decision, error.code, error.message)
            if self._queue.full():
                return self._reject(
                    decision, "output_backpressure", "output queue is full"
                )
            batch = ExecutionBatch(
                batch_id=EventId(f"execution_batch_{uuid4().hex}"),
                plan_id=plan.plan_id,
                turn_id=plan.turn_id,
                accepted_at=self._clock(),
                intent_ids=tuple(intent.intent_id for intent in plan.intents),
            )
            runtime = BatchRuntime(batch, plan)
            if self._journal is not None:
                try:
                    self._journal.record_decision(decision)
                except (OSError, RuntimeError, ValueError) as error:
                    return self._reject(
                        decision,
                        "journal_unavailable",
                        f"decision was not durably journaled: {type(error).__name__}",
                        record_journal=False,
                    )
            if self._decision_handler is not None:
                try:
                    self._decision_handler(decision)
                except (OSError, RuntimeError, ValueError) as error:
                    return self._reject(
                        decision,
                        "context_checkpoint_unavailable",
                        "reply projection was not durably checkpointed: "
                        f"{type(error).__name__}",
                    )
            self._decisions[str(plan.plan_id)] = decision
            self._runtimes[plan.turn_id] = runtime
            self._trim_completed_locked()
            for intent in plan.intents:
                kind, _executor = self._executors.for_intent(intent)
                self._emit(
                    plan,
                    intent,
                    kind,
                    ExecutionStatus.ACCEPTED,
                    None,
                    interaction_scope=decision.interaction_scope,
                )
            self._queue.put_nowait(runtime)
        return batch

    def accept(self, decision: TurnDecision) -> bool:
        """Accept only the governed decision produced by BrainCoordinator."""
        return isinstance(self.submit(decision), ExecutionBatch)

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

    def decision(self, turn_id: TurnId) -> Optional[TurnDecision]:
        with self._lock:
            runtime = self._runtimes.get(turn_id)
            if runtime is None:
                return None
            return self._decisions.get(str(runtime.plan.plan_id))

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

    def _validate(self, decision: TurnDecision) -> Optional[ErrorInfo]:
        from elfie.brain.reasoning.execution_validation import (
            validate_plan_for_execution,
        )

        body_id, body_generation = _body_target(decision)
        return validate_plan_for_execution(
            decision.plan,
            self._capabilities.current(),
            now=self._clock(),
            max_intents=self._max_intents,
            max_schedule_horizon=self._max_schedule_horizon,
            expected_body_id=body_id,
            expected_body_generation=body_generation,
        )

    def _validate_intent(
        self,
        plan: DecisionPlan,
        _intent: DecisionIntent,
    ) -> Optional[ErrorInfo]:
        from elfie.brain.reasoning.execution_validation import (
            validate_plan_for_execution,
        )

        with self._lock:
            decision = self._decisions.get(str(plan.plan_id))
        body_id, body_generation = _body_target(decision)
        return validate_plan_for_execution(
            plan,
            self._capabilities.current(),
            now=self._clock(),
            max_intents=self._max_intents,
            max_schedule_horizon=self._max_schedule_horizon,
            expected_body_id=body_id,
            expected_body_generation=body_generation,
        )

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
        *,
        interaction_scope: InteractionScope | None = None,
    ) -> None:
        publish_to_workspace = (
            not isinstance(intent, NoOpIntent)
            and status not in {ExecutionStatus.ACCEPTED, ExecutionStatus.STARTED}
            and not (
                kind is ExecutorKind.BODY
                and bool(
                    getattr(
                        self._body_executor,
                        "publishes_embodied_outcome",
                        False,
                    )
                )
            )
        )
        if publish_to_workspace and interaction_scope is None:
            with self._lock:
                decision = self._decisions.get(str(plan.plan_id))
            interaction_scope = None if decision is None else decision.interaction_scope
        receipt = self._publisher.emit(
            plan=plan,
            intent=intent,
            executor=kind,
            status=status,
            error=error,
            # A NoOp is already the terminal interpretation of the current
            # frame. Re-publishing its own receipts would create an endless
            # receipt-only cognition loop. The receipt remains available to
            # journaling and settlement below.
            publish_to_workspace=publish_to_workspace,
            interaction_scope=interaction_scope,
        )
        if self._journal is not None:
            self._journal.record_receipt(receipt)
        if self._receipt_handler is not None:
            self._receipt_handler(plan, intent, receipt)

    def _reject(
        self,
        decision: TurnDecision,
        code: str,
        message: str,
        *,
        record_journal: bool = True,
    ) -> BatchRejection:
        plan = decision.plan
        if record_journal and self._journal is not None:
            try:
                self._journal.record_rejection(decision, code)
            except (OSError, RuntimeError, ValueError):
                code = "journal_unavailable"
                message = "decision rejection could not be durably journaled"
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
            self._decisions.pop(str(runtime.plan.plan_id), None)
            self._evicted_completed_count += 1


def _body_target(
    decision: TurnDecision | None,
) -> tuple[str | None, int | None]:
    """Return the immutable embodied target captured by a decision."""
    if decision is None or not isinstance(decision.interaction_scope, EmbodiedScope):
        return None, None
    return (
        decision.interaction_scope.body_id,
        decision.interaction_scope.body_generation,
    )


__all__ = ("OutputRouter",)


def _closed_activity_executor() -> IntentExecutor:
    from elfie.brain.reasoning.internal_execution import ClosedActivityIntentExecutor

    return ClosedActivityIntentExecutor()
