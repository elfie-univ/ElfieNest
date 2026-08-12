"""Restricted executor for internal operations and audit-only NoOp intents."""

from __future__ import annotations

from functools import singledispatch
from typing import Callable, Protocol

from elfie.brain.activity import (
    ActivityPreflightStatus,
    ActivityStateEvent,
    ActivityStorePort,
    activity_scope_for_record,
    activity_state_event_to_perception,
)
from elfie.brain.decision_types import (
    DecisionIntent,
    DecisionPlan,
    InternalIntent,
    NoOpIntent,
    PersistentActivityIntent,
)
from elfie.brain.output_types import IntentExecutionResult
from elfie.brain.workspace_ports import PerceptionSink
from elfie.message_types import ElfieId, ErrorInfo, IntentId, TurnId, UTCDateTime


class InternalIntentSink(Protocol):
    def execute(
        self,
        plan: DecisionPlan,
        intent: InternalIntent,
    ) -> IntentExecutionResult:
        """Execute one operation from the closed InternalOperation set."""


class ClosedInternalIntentSink:
    """Acknowledge the current closed operations until Activity exists."""

    def execute(
        self,
        plan: DecisionPlan,
        intent: InternalIntent,
    ) -> IntentExecutionResult:
        del plan, intent
        return IntentExecutionResult.completed()


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


class PersistentActivityIntentExecutor:
    """Preflight and commit validated Activity requests at the output boundary."""

    def __init__(
        self,
        store: ActivityStorePort,
        clock,
        *,
        elfie_id: ElfieId | None = None,
        trigger_sink: PerceptionSink | None = None,
        on_trigger: Callable[[], None] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._elfie_id = elfie_id
        self._trigger_sink = trigger_sink
        self._on_trigger = on_trigger

    def preflight(self, plan: DecisionPlan, intent: DecisionIntent):
        del plan
        if not isinstance(intent, PersistentActivityIntent):
            return None
        checked_at: UTCDateTime = self._clock()
        result = self._store.preflight(intent.draft, now=checked_at)
        if result.status is ActivityPreflightStatus.VALIDATED:
            return None
        return (
            result.reasons[0]
            if result.reasons
            else ErrorInfo(
                code="activity_preflight_rejected",
                message="Activity Preflight rejected the draft",
            )
        )

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        del plan
        if not isinstance(intent, PersistentActivityIntent):
            return IntentExecutionResult.failed(
                ErrorInfo(
                    code="activity_intent_type", message="invalid Activity intent"
                )
            )
        result = self._store.preflight(intent.draft, now=self._clock())
        if result.status is not ActivityPreflightStatus.VALIDATED:
            return IntentExecutionResult.failed(
                result.reasons[0]
                if result.reasons
                else ErrorInfo(
                    code="activity_preflight_rejected",
                    message="Activity Preflight rejected the draft",
                )
            )
        try:
            record = self._store.commit(intent.draft, preflight=result)
        except Exception as error:  # noqa: BLE001 - semantic Port boundary
            return IntentExecutionResult.failed(
                ErrorInfo(code=type(error).__name__, message=str(error))
            )
        if (
            record.state.value == "running"
            and self._elfie_id is not None
            and self._trigger_sink is not None
        ):
            self._publish_trigger(record)
        return IntentExecutionResult.completed()

    def _publish_trigger(self, record) -> None:
        if self._elfie_id is None or self._trigger_sink is None:
            return
        event = ActivityStateEvent(
            activity_id=record.activity_id,
            revision=record.revision,
            state=record.state,
            occurred_at=self._clock(),
            causation_event_ids=record.draft.cause_event_ids,
            next_wakeup_at=record.next_wakeup_at,
            reason="activity_committed",
        )
        self._trigger_sink.publish(
            activity_state_event_to_perception(
                event,
                elfie_id=self._elfie_id,
                response_scope=activity_scope_for_record(record),
            )
        )
        if self._on_trigger is not None:
            self._on_trigger()

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        del turn_id, intent_id, reason


class ClosedActivityIntentExecutor(PersistentActivityIntentExecutor):
    """Reject Activity requests when a host did not inject an Activity store."""

    def __init__(self) -> None:
        # The overridden methods never access the base executor state.
        pass

    def preflight(self, plan: DecisionPlan, intent: DecisionIntent):
        del plan
        if isinstance(intent, PersistentActivityIntent):
            return ErrorInfo(
                code="activity_store_unavailable",
                message="Persistent Activity storage is not configured",
            )
        return None

    def execute(
        self, plan: DecisionPlan, intent: DecisionIntent
    ) -> IntentExecutionResult:
        del plan, intent
        return IntentExecutionResult.failed(
            ErrorInfo(
                code="activity_store_unavailable",
                message="Persistent Activity storage is not configured",
            )
        )


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


__all__ = (
    "ClosedInternalIntentSink",
    "ClosedActivityIntentExecutor",
    "InternalIntentExecutor",
    "InternalIntentSink",
    "PersistentActivityIntentExecutor",
)
