"""Terminal completion handling outside the coordinator mailbox loop."""

from __future__ import annotations

from elfie.brain.reasoning.coordinator_outcomes import reasoning_failure_outcome
from elfie.brain.reasoning.coordinator_ports import TurnDecisionSink
from elfie.brain.reasoning.coordinator_runtime import TurnOutcomeBuffer
from elfie.brain.reasoning.coordinator_types import InFlightTurn, WorkerDoneControl
from elfie.brain.reasoning.decision_governance import govern_decision
from elfie.brain.reasoning.run import ReasoningStatus
from elfie.brain.reasoning.settlement import TurnSettlementPort
from elfie.brain.reasoning.turn_outcome import TerminalStatus
from elfie.brain.workspace.system import EventWorkspace


class CoordinatorCompletionHandler:
    """Close a completed Future against its claimed frame exactly once."""

    def __init__(
        self,
        *,
        workspace: EventWorkspace,
        plan_sink: TurnDecisionSink,
        outcomes: TurnOutcomeBuffer,
        settlement: TurnSettlementPort,
    ) -> None:
        self._workspace = workspace
        self._plan_sink = plan_sink
        self._outcomes = outcomes
        self._settlement = settlement

    def complete(
        self,
        inflight: InFlightTurn,
        control: WorkerDoneControl,
    ) -> None:
        """Commit, release, or discard one late model result."""
        try:
            result = control.future.result()
        except Exception as error:  # noqa: BLE001 - Future boundary owns failure mapping
            self._workspace.release(
                inflight.frame.frame_id,
                inflight.task.seed.turn_id,
                type(error).__name__,
            )
            self._outcomes.record(
                reasoning_failure_outcome(
                    turn_id=inflight.task.seed.turn_id,
                    frame_id=inflight.frame.frame_id,
                    error_code=type(error).__name__,
                )
            )
            return
        if inflight.terminal_status is TerminalStatus.STALE:
            self._workspace.commit(inflight.frame.frame_id, inflight.task.seed.turn_id)
            self._outcomes.record(
                result.decode.report.to_turn_outcome(
                    plan=result.decode.plan,
                    status=TerminalStatus.STALE,
                    stale_reason=inflight.terminal_reason,
                )
            )
            return
        try:
            self._settlement.settle(inflight.task.state_candidates)
        except Exception as error:  # noqa: BLE001 - owner commit boundary
            self._workspace.release(
                inflight.frame.frame_id,
                inflight.task.seed.turn_id,
                "turn_settlement_failed",
            )
            self._outcomes.record(
                reasoning_failure_outcome(
                    turn_id=inflight.task.seed.turn_id,
                    frame_id=inflight.frame.frame_id,
                    error_code=f"turn_settlement_failed:{type(error).__name__}",
                )
            )
            return
        decision = govern_decision(inflight.frame, result.decode.plan)
        if result.reasoning.status not in {
            ReasoningStatus.COMPLETED,
            ReasoningStatus.SAFE_NOOP,
        }:
            if self._plan_sink.accept(decision):
                self._workspace.commit(
                    inflight.frame.frame_id,
                    inflight.task.seed.turn_id,
                )
            else:
                self._workspace.release(
                    inflight.frame.frame_id,
                    inflight.task.seed.turn_id,
                    "reasoning_failed_router_rejected",
                )
            self._outcomes.record(
                result.decode.report.to_turn_outcome(
                    plan=decision.plan,
                    status=TerminalStatus.FAILED,
                    error_code=result.reasoning.failure_reason
                    or result.reasoning.status.value,
                )
            )
            return
        if self._plan_sink.accept(decision):
            self._workspace.commit(inflight.frame.frame_id, inflight.task.seed.turn_id)
            self._outcomes.record(
                result.decode.report.to_turn_outcome(
                    plan=decision.plan,
                    status=TerminalStatus.COMPLETED,
                )
            )
            return
        self._workspace.release(
            inflight.frame.frame_id,
            inflight.task.seed.turn_id,
            "router_rejected",
        )
        self._outcomes.record(
            result.decode.report.to_turn_outcome(
                plan=decision.plan,
                status=TerminalStatus.FAILED,
                error_code="router_rejected",
            )
        )


__all__ = ("CoordinatorCompletionHandler",)
