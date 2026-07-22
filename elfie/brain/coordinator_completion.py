"""Terminal completion handling outside the coordinator mailbox loop."""

from __future__ import annotations

from elfie.brain.coordinator_outcomes import cortical_failure_outcome
from elfie.brain.coordinator_ports import DecisionPlanSink
from elfie.brain.coordinator_runtime import TurnOutcomeBuffer
from elfie.brain.coordinator_types import InFlightTurn, WorkerDoneControl
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.turn_outcome import TerminalStatus


class CoordinatorCompletionHandler:
    """Close a completed Future against its claimed frame exactly once."""

    def __init__(
        self,
        *,
        workspace: PerceptualWorkspace,
        plan_sink: DecisionPlanSink,
        outcomes: TurnOutcomeBuffer,
    ) -> None:
        self._workspace = workspace
        self._plan_sink = plan_sink
        self._outcomes = outcomes

    def complete(
        self,
        inflight: InFlightTurn,
        control: WorkerDoneControl,
    ) -> None:
        """Commit, release, or discard one late model result."""
        try:
            result = control.future.result()
        except Exception as error:  # noqa: BROAD_EXCEPT_OK  # noqa: BLE001 - Future boundary
            self._workspace.release(
                inflight.frame.frame_id,
                inflight.task.seed.turn_id,
                type(error).__name__,
            )
            self._outcomes.record(
                cortical_failure_outcome(
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
        if self._plan_sink.accept(result.decode.plan):
            self._workspace.commit(inflight.frame.frame_id, inflight.task.seed.turn_id)
            self._outcomes.record(
                result.decode.report.to_turn_outcome(
                    plan=result.decode.plan,
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
                plan=result.decode.plan,
                status=TerminalStatus.FAILED,
                error_code="router_rejected",
            )
        )


__all__ = ("CoordinatorCompletionHandler",)
