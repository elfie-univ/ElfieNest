"""Terminal completion handling outside the coordinator mailbox loop."""

from __future__ import annotations

import logging
from collections import OrderedDict
from enum import Enum, unique
from typing import Literal

from elfie.brain.memory.memory_records import MemoryUseProposal
from elfie.brain.reasoning.coordinator_outcomes import reasoning_failure_outcome
from elfie.brain.reasoning.coordinator_ports import TurnDecisionSink
from elfie.brain.reasoning.coordinator_runtime import TurnOutcomeBuffer
from elfie.brain.reasoning.coordinator_types import InFlightTurn, WorkerDoneControl
from elfie.brain.reasoning.decision_governance import govern_decision
from elfie.brain.reasoning.run import ReasoningStatus
from elfie.brain.reasoning.settlement import TurnSettlementPort
from elfie.brain.reasoning.turn_outcome import TerminalStatus
from elfie.brain.workspace.system import EventWorkspace
from elfie.brain.workspace.types import ReleaseDisposition


@unique
class CompletionDisposition(str, Enum):
    """Frame outcome needed by process-local affect transaction ownership."""

    COMMITTED = "committed"
    REPLAY = "replay"
    DEAD_LETTERED = "dead_lettered"


logger = logging.getLogger("elfie.brain.reasoning.memory_use")
MemoryTargetKind = Literal["episode", "node", "assertion"]


class CoordinatorCompletionHandler:
    """Close a completed Future against its claimed frame exactly once."""

    def __init__(
        self,
        *,
        workspace: EventWorkspace,
        plan_sink: TurnDecisionSink,
        outcomes: TurnOutcomeBuffer,
        settlement: TurnSettlementPort,
        context_source=None,
    ) -> None:
        self._workspace = workspace
        self._plan_sink = plan_sink
        self._outcomes = outcomes
        self._settlement = settlement
        self._context_source = context_source

    def complete(
        self,
        inflight: InFlightTurn,
        control: WorkerDoneControl,
    ) -> CompletionDisposition:
        """Commit, release, or discard one late model result."""
        try:
            result = control.future.result()
        except Exception as error:  # noqa: BLE001 - Future boundary owns failure mapping
            released = self._workspace.release(
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
            return _released_disposition(released)
        if inflight.terminal_status is TerminalStatus.STALE:
            self._workspace.commit(inflight.frame.frame_id, inflight.task.seed.turn_id)
            self._outcomes.record(
                result.decode.report.to_turn_outcome(
                    plan=result.decode.plan,
                    status=TerminalStatus.STALE,
                    stale_reason=inflight.terminal_reason,
                )
            )
            return CompletionDisposition.COMMITTED
        try:
            self._settlement.settle(inflight.task.state_candidates)
        except Exception as error:  # noqa: BLE001 - owner commit boundary
            released = self._workspace.release(
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
            return _released_disposition(released)
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
                disposition = CompletionDisposition.COMMITTED
            else:
                released = self._workspace.release(
                    inflight.frame.frame_id,
                    inflight.task.seed.turn_id,
                    "reasoning_failed_router_rejected",
                )
                disposition = _released_disposition(released)
            self._outcomes.record(
                result.decode.report.to_turn_outcome(
                    plan=decision.plan,
                    status=TerminalStatus.FAILED,
                    error_code=result.reasoning.failure_reason
                    or result.reasoning.status.value,
                )
            )
            return disposition
        if self._plan_sink.accept(decision):
            self._workspace.commit(inflight.frame.frame_id, inflight.task.seed.turn_id)
            if result.reasoning.status is ReasoningStatus.COMPLETED:
                self._submit_memory_use_proposals(inflight, result.decode.plan)
            self._outcomes.record(
                result.decode.report.to_turn_outcome(
                    plan=decision.plan,
                    status=TerminalStatus.COMPLETED,
                )
            )
            return CompletionDisposition.COMMITTED
        released = self._workspace.release(
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
        return _released_disposition(released)

    def _submit_memory_use_proposals(self, inflight: InFlightTurn, plan) -> None:
        """Record bounded model references; never turn them into reinforcement."""
        if self._context_source is None or not plan.memory_uses:
            return
        submit = getattr(self._context_source, "submit_memory_use_proposal", None)
        if not callable(submit):
            return
        grouped: OrderedDict[MemoryTargetKind, list] = OrderedDict()
        for reference in plan.memory_uses:
            grouped.setdefault(reference.target_kind, []).append(reference)
        occurred_at = inflight.task.seed.created_at.isoformat()
        for target_kind, references in grouped.items():
            target_ids = tuple(
                dict.fromkeys(str(item.target_id) for item in references)
            )
            claim_refs = tuple(
                dict.fromkeys(
                    str(item.claim_ref)
                    for item in references
                    if item.claim_ref is not None
                )
            )
            proposal = MemoryUseProposal(
                proposal_id=f"memory-use:{plan.plan_id}:{target_kind}",
                recall_revision=getattr(inflight.task, "memory_recall_revision", 0),
                occurred_at=occurred_at,
                target_kind=target_kind,
                target_ids=target_ids,
                claim_refs=claim_refs,
            )
            try:
                submit(str(inflight.frame.frame_id), proposal)
            except Exception as error:  # noqa: BLE001 - proposal is advisory
                logger.warning(
                    "discarding invalid memory-use proposal for frame %s: %s",
                    inflight.frame.frame_id,
                    error,
                )


def _released_disposition(released: ReleaseDisposition) -> CompletionDisposition:
    if released is ReleaseDisposition.DEAD_LETTERED:
        return CompletionDisposition.DEAD_LETTERED
    return CompletionDisposition.REPLAY


__all__ = ("CompletionDisposition", "CoordinatorCompletionHandler")
