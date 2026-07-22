"""Terminal outcome construction for BrainCoordinator closures."""

from elfie.brain.decision_types import DecisionPlan
from elfie.brain.turn_outcome import ModelMode, TerminalStatus, TurnOutcome
from elfie.message_types import EventId, PlanId, TurnId


def cortical_timeout_outcome(plan: DecisionPlan) -> TurnOutcome:
    """Describe a coordinator-owned hard timeout without rich tracing."""
    return TurnOutcome(
        turn_id=plan.turn_id,
        frame_id=plan.frame_id,
        plan_id=plan.plan_id,
        status=TerminalStatus.TIMED_OUT,
        model_mode=ModelMode.NO_OP,
        fallback_reason="cortical_hard_timeout",
        timeout_reason="cortical_hard_timeout",
        stale_reason=None,
        error_code=None,
        receipt_ids=(),
    )


def cortical_failure_outcome(
    *,
    turn_id: TurnId,
    frame_id: EventId,
    error_code: str,
) -> TurnOutcome:
    """Describe a failed turn even when no model plan could be constructed."""
    return TurnOutcome(
        turn_id=turn_id,
        frame_id=frame_id,
        plan_id=PlanId(f"failed-{turn_id}"),
        status=TerminalStatus.FAILED,
        model_mode=ModelMode.NO_OP,
        fallback_reason=None,
        timeout_reason=None,
        stale_reason=None,
        error_code=error_code,
        receipt_ids=(),
    )


__all__ = ("cortical_failure_outcome", "cortical_timeout_outcome")
