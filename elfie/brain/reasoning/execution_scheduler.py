"""Dependency-aware execution state machine for accepted output batches."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from functools import singledispatch
from threading import Event
from typing import Callable, Iterable, Optional, Tuple

from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionIntent,
    DecisionPlan,
    MessageIntent,
)
from elfie.brain.reasoning.execution_ports import IntentExecutor
from elfie.brain.reasoning.execution_state import BatchRuntime, ExecutorRegistry
from elfie.brain.reasoning.execution_types import (
    ExecutorKind,
    IntentExecutionResult,
)
from elfie.brain.workspace.contracts import ExecutionStatus
from elfie.message_types import ErrorInfo, UTCDateTime

EmitReceipt = Callable[
    [DecisionPlan, DecisionIntent, ExecutorKind, ExecutionStatus, Optional[ErrorInfo]],
    None,
]
CapabilityCheck = Callable[[DecisionPlan, DecisionIntent], Optional[ErrorInfo]]
WaitUntil = Callable[[UTCDateTime, Event], bool]


class OutputBatchScheduler:
    """Run dependency waves while preserving per-sequence message order."""

    def __init__(
        self,
        *,
        pool: ThreadPoolExecutor,
        executors: ExecutorRegistry,
        emit: EmitReceipt,
        capability_check: CapabilityCheck,
        wait_until: WaitUntil,
    ) -> None:
        self._pool = pool
        self._executors = executors
        self._emit = emit
        self._capability_check = capability_check
        self._wait_until = wait_until

    def execute(self, runtime: BatchRuntime) -> None:
        pending = list(runtime.plan.intents)
        while pending:
            pending = self._cancel_blocked(runtime, pending)
            if not pending:
                break
            ready = tuple(
                intent for intent in pending if self._is_ready(runtime, intent, pending)
            )
            if not ready:
                self._cancel_deadlock(runtime, pending)
                break
            futures = self._start_ready(runtime, ready)
            for intent, future in futures:
                try:
                    result = future.result()
                except (OSError, RuntimeError) as error:
                    result = IntentExecutionResult.failed(
                        ErrorInfo(code=type(error).__name__, message=str(error))
                    )
                kind, _executor = self._executors.for_intent(intent)
                self._emit(
                    runtime.plan,
                    intent,
                    kind,
                    result.status,
                    result.error,
                )
                with runtime.lock:
                    runtime.statuses[intent.intent_id] = result.status
                    runtime.running.pop(intent.intent_id, None)
            ready_ids = {intent.intent_id for intent in ready}
            pending = [
                intent for intent in pending if intent.intent_id not in ready_ids
            ]
            if pending and _has_pending_sequence_successor(ready, pending):
                # A completed message is already true, but an emergency posted
                # at that boundary must be able to cancel the not-yet-started
                # successor. Event.wait both yields the scheduler thread and
                # wakes immediately when cancellation is signalled.
                runtime.cancelled.wait(0.005)
        runtime.done.set()

    def _start_ready(
        self,
        runtime: BatchRuntime,
        ready: Tuple[DecisionIntent, ...],
    ) -> Tuple[tuple[DecisionIntent, Future[IntentExecutionResult]], ...]:
        futures: list[tuple[DecisionIntent, Future[IntentExecutionResult]]] = []
        for intent in ready:
            kind, executor = self._executors.for_intent(intent)
            error = self._capability_check(runtime.plan, intent)
            if error is not None:
                self._emit(runtime.plan, intent, kind, ExecutionStatus.FAILED, error)
                with runtime.lock:
                    runtime.statuses[intent.intent_id] = ExecutionStatus.FAILED
                continue
            futures.append(
                (
                    intent,
                    self._pool.submit(
                        self._execute_when_due,
                        runtime,
                        intent,
                        kind,
                        executor,
                    ),
                )
            )
        return tuple(futures)

    def _execute_when_due(
        self,
        runtime: BatchRuntime,
        intent: DecisionIntent,
        kind: ExecutorKind,
        executor: IntentExecutor,
    ) -> IntentExecutionResult:
        send_after = intent_send_after(intent)
        if send_after is not None and not self._wait_until(
            send_after, runtime.cancelled
        ):
            return IntentExecutionResult(
                ExecutionStatus.CANCELLED,
                ErrorInfo(
                    code="stale_turn", message=runtime.cancel_reason or "stale turn"
                ),
            )
        capability_error = self._capability_check(runtime.plan, intent)
        if capability_error is not None:
            return IntentExecutionResult.failed(capability_error)
        self._emit(runtime.plan, intent, kind, ExecutionStatus.STARTED, None)
        with runtime.lock:
            runtime.running[intent.intent_id] = intent
        return executor.execute(runtime.plan, intent)

    def _cancel_blocked(
        self,
        runtime: BatchRuntime,
        pending: list[DecisionIntent],
    ) -> list[DecisionIntent]:
        retained: list[DecisionIntent] = []
        for intent in pending:
            dependency_failed = any(
                runtime.statuses.get(dependency)
                not in {None, ExecutionStatus.COMPLETED}
                for dependency in intent.dependency_ids
            )
            stale_cancel = runtime.cancelled.is_set() and (
                intent.cancel_policy is not CancelPolicy.NEVER
            )
            if dependency_failed:
                self._cancel(runtime, intent, "cancelled_dependency")
            elif stale_cancel:
                self._cancel(runtime, intent, runtime.cancel_reason or "stale_turn")
            else:
                retained.append(intent)
        return retained

    def _cancel(self, runtime: BatchRuntime, intent: DecisionIntent, code: str) -> None:
        kind, _executor = self._executors.for_intent(intent)
        error = ErrorInfo(code=code, message=code)
        self._emit(runtime.plan, intent, kind, ExecutionStatus.CANCELLED, error)
        runtime.statuses[intent.intent_id] = ExecutionStatus.CANCELLED

    def _is_ready(
        self,
        runtime: BatchRuntime,
        intent: DecisionIntent,
        pending: Iterable[DecisionIntent],
    ) -> bool:
        dependencies_ready = all(
            runtime.statuses.get(dependency) is ExecutionStatus.COMPLETED
            for dependency in intent.dependency_ids
        )
        return dependencies_ready and _sequence_ready(intent, pending)

    def _cancel_deadlock(
        self,
        runtime: BatchRuntime,
        pending: Iterable[DecisionIntent],
    ) -> None:
        for intent in pending:
            self._cancel(runtime, intent, "scheduler_deadlock")


@singledispatch
def _sequence_ready(
    _intent: DecisionIntent, _pending: Iterable[DecisionIntent]
) -> bool:
    return True


@_sequence_ready.register
def _message_sequence_ready(
    intent: MessageIntent,
    pending: Iterable[DecisionIntent],
) -> bool:
    if intent.sequence_id is None:
        return True
    earlier = (
        candidate
        for candidate in pending
        if isinstance(candidate, MessageIntent)
        and candidate.sequence_id == intent.sequence_id
        and (candidate.ordinal or 0) < (intent.ordinal or 0)
    )
    return next(earlier, None) is None


def _has_pending_sequence_successor(
    completed: Iterable[DecisionIntent],
    pending: Iterable[DecisionIntent],
) -> bool:
    sequence_ids = {
        item.sequence_id
        for item in completed
        if isinstance(item, MessageIntent) and item.sequence_id is not None
    }
    return any(
        isinstance(item, MessageIntent) and item.sequence_id in sequence_ids
        for item in pending
    )


@singledispatch
def intent_send_after(_intent: DecisionIntent) -> Optional[UTCDateTime]:
    return None


@intent_send_after.register
def _message_send_after(intent: MessageIntent) -> Optional[UTCDateTime]:
    return intent.send_after


__all__ = (
    "OutputBatchScheduler",
    "intent_send_after",
)
