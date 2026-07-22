"""Restricted executor for internal operations and audit-only NoOp intents."""

from functools import singledispatch
from typing import Protocol

from elfie.brain.decision_types import (
    DecisionIntent,
    DecisionPlan,
    InternalIntent,
    NoOpIntent,
)
from elfie.brain.output_types import IntentExecutionResult
from elfie.message_types import IntentId, TurnId


class InternalIntentSink(Protocol):
    def execute(
        self,
        plan: DecisionPlan,
        intent: InternalIntent,
    ) -> IntentExecutionResult:
        """Execute one operation from the closed InternalOperation set."""


class InternalIntentExecutor:
    """Keep internal operations explicit and make NoOp audit-only."""

    def __init__(self, sink: InternalIntentSink) -> None:
        self._sink = sink

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        return _execute_internal(intent, plan, self._sink)

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        del turn_id, intent_id, reason


@singledispatch
def _execute_internal(
    intent: DecisionIntent,
    _plan: DecisionPlan,
    _sink: InternalIntentSink,
) -> IntentExecutionResult:
    raise TypeError(type(intent).__name__)


@_execute_internal.register
def _execute_operation(
    intent: InternalIntent,
    plan: DecisionPlan,
    sink: InternalIntentSink,
) -> IntentExecutionResult:
    return sink.execute(plan, intent)


@_execute_internal.register
def _complete_noop(
    _intent: NoOpIntent,
    _plan: DecisionPlan,
    _sink: InternalIntentSink,
) -> IntentExecutionResult:
    return IntentExecutionResult.completed()


__all__ = ("InternalIntentExecutor", "InternalIntentSink")
