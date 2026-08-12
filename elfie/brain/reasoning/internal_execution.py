"""Audit-only NoOp and validated Persistent Activity execution."""

from __future__ import annotations

from typing import Callable

from elfie.brain.activity.preflight import ActivityCommitPort
from elfie.brain.activity.system import (
    ActivityStateEvent,
    activity_scope_for_record,
    activity_state_event_to_perception,
)
from elfie.brain.reasoning.decision_types import (
    DecisionIntent,
    DecisionPlan,
    NoOpIntent,
    PersistentActivityRequest,
)
from elfie.brain.reasoning.execution_types import IntentExecutionResult
from elfie.brain.workspace.ports import PerceptionSink
from elfie.message_types import ElfieId, ErrorInfo, IntentId, TurnId


class NoOpExecutor:
    """Complete only a genuine No-op; state changes use Turn Settlement."""

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        del plan
        if not isinstance(intent, NoOpIntent):
            return IntentExecutionResult.failed(
                ErrorInfo(
                    code="internal_output_forbidden",
                    message="Internal state changes must use Turn Settlement",
                )
            )
        return IntentExecutionResult.completed()

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        del turn_id, intent_id, reason


class PersistentActivityRequestExecutor:
    """Commit only the Preflight evidence produced by the same ReasoningRun."""

    def __init__(
        self,
        committer: ActivityCommitPort,
        clock,
        *,
        elfie_id: ElfieId | None = None,
        trigger_sink: PerceptionSink | None = None,
        on_trigger: Callable[[], None] | None = None,
    ) -> None:
        self._committer = committer
        self._clock = clock
        self._elfie_id = elfie_id
        self._trigger_sink = trigger_sink
        self._on_trigger = on_trigger

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        del plan
        if not isinstance(intent, PersistentActivityRequest):
            return IntentExecutionResult.failed(
                ErrorInfo(
                    code="activity_intent_type", message="invalid Activity intent"
                )
            )
        result = intent.preflight
        if result is None:
            return IntentExecutionResult.failed(
                ErrorInfo(
                    code="activity_preflight_missing",
                    message="Activity request has no same-run Preflight evidence",
                )
            )
        try:
            record = self._committer.commit(intent.draft, result)
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


class ClosedActivityIntentExecutor(PersistentActivityRequestExecutor):
    """Reject Activity requests when a host did not inject an Activity store."""

    def __init__(self) -> None:
        # The overridden methods never access the base executor state.
        pass

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


__all__ = (
    "ClosedActivityIntentExecutor",
    "NoOpExecutor",
    "PersistentActivityRequestExecutor",
)
