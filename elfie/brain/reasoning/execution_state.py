"""Mutable batch runtime and closed executor target resolution."""

from __future__ import annotations

from functools import singledispatch
from threading import Event, Lock
from typing import Dict, Optional, Tuple

from elfie.brain.reasoning.decision_types import (
    CapabilityIntent,
    DecisionIntent,
    DecisionPlan,
    MessageIntent,
    NoOpIntent,
    PersistentActivityRequest,
)
from elfie.brain.reasoning.execution_ports import IntentExecutor
from elfie.brain.reasoning.execution_types import ExecutionBatch, ExecutorKind
from elfie.brain.workspace.contracts import ExecutionStatus
from elfie.message_types import IntentId


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
        activity: IntentExecutor,
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


@singledispatch
def executor_kind(intent: DecisionIntent) -> ExecutorKind:
    raise TypeError(type(intent).__name__)


@executor_kind.register(CapabilityIntent)
def _body_kind(_intent: DecisionIntent) -> ExecutorKind:
    return ExecutorKind.BODY


@executor_kind.register(MessageIntent)
def _communication_kind(_intent: MessageIntent) -> ExecutorKind:
    return ExecutorKind.COMMUNICATION


@executor_kind.register(NoOpIntent)
def _internal_kind(_intent: DecisionIntent) -> ExecutorKind:
    return ExecutorKind.INTERNAL


@executor_kind.register(PersistentActivityRequest)
def _activity_kind(_intent: PersistentActivityRequest) -> ExecutorKind:
    return ExecutorKind.ACTIVITY


__all__ = ("BatchRuntime", "ExecutorRegistry", "executor_kind")
