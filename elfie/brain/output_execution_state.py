"""Mutable batch runtime and closed executor target resolution."""

from __future__ import annotations

from functools import singledispatch
from threading import Event, Lock
from typing import Dict, Optional, Tuple, cast

from elfie.brain.decision_types import (
    DecisionIntent,
    DecisionPlan,
    ExpressionIntent,
    InternalIntent,
    MessageIntent,
    MotionIntent,
    NoOpIntent,
    PersistentActivityIntent,
    SpeechIntent,
)
from elfie.brain.output_ports import ActivityPreflightExecutor, IntentExecutor
from elfie.brain.output_types import ExecutionBatch, ExecutorKind
from elfie.brain.perception_types import ExecutionStatus
from elfie.message_types import ErrorInfo, IntentId


class BatchRuntime:
    """Mutable batch state shared only by Router and its scheduler."""

    def __init__(self, batch: ExecutionBatch, plan: DecisionPlan) -> None:
        self.batch = batch
        self.plan = plan
        self.done = Event()
        self.cancelled = Event()
        self.cancel_reason: Optional[str] = None
        self.statuses: Dict[IntentId, ExecutionStatus] = {}
        self.running: Dict[IntentId, DecisionIntent] = {}
        self.lock = Lock()

    def cancel(self, reason: str) -> Tuple[DecisionIntent, ...]:
        with self.lock:
            self.cancel_reason = reason
            self.cancelled.set()
            return tuple(self.running.values())


class ExecutorRegistry:
    """Resolve the closed executor target set without exposing scheduler internals."""

    def __init__(
        self,
        *,
        body: IntentExecutor,
        communication: IntentExecutor,
        internal: IntentExecutor,
        activity: ActivityPreflightExecutor,
    ) -> None:
        self._executors = {
            ExecutorKind.BODY: body,
            ExecutorKind.COMMUNICATION: communication,
            ExecutorKind.INTERNAL: internal,
            ExecutorKind.ACTIVITY: activity,
        }

    def for_intent(self, intent: DecisionIntent) -> tuple[ExecutorKind, IntentExecutor]:
        kind = executor_kind(intent)
        return kind, self._executors[kind]

    def preflight(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> ErrorInfo | None:
        kind = executor_kind(intent)
        executor = self._executors[kind]
        if kind is not ExecutorKind.ACTIVITY:
            return None
        return cast(ActivityPreflightExecutor, executor).preflight(plan, intent)


@singledispatch
def executor_kind(intent: DecisionIntent) -> ExecutorKind:
    raise TypeError(type(intent).__name__)


@executor_kind.register(SpeechIntent)
@executor_kind.register(MotionIntent)
@executor_kind.register(ExpressionIntent)
def _body_kind(_intent: DecisionIntent) -> ExecutorKind:
    return ExecutorKind.BODY


@executor_kind.register(MessageIntent)
def _communication_kind(_intent: MessageIntent) -> ExecutorKind:
    return ExecutorKind.COMMUNICATION


@executor_kind.register(InternalIntent)
@executor_kind.register(NoOpIntent)
def _internal_kind(_intent: DecisionIntent) -> ExecutorKind:
    return ExecutorKind.INTERNAL


@executor_kind.register(PersistentActivityIntent)
def _activity_kind(_intent: PersistentActivityIntent) -> ExecutorKind:
    return ExecutorKind.ACTIVITY


__all__ = ("BatchRuntime", "ExecutorRegistry", "executor_kind")
