"""Deterministic conversion from a model proposal to one scoped turn decision."""

from pydantic import ValidationError

from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionPlan,
    NoOpIntent,
    TurnDecision,
)
from elfie.brain.workspace.contracts import TurnFrame
from elfie.message_types import IntentId, PlanId


def govern_decision(
    frame: TurnFrame,
    proposal: DecisionPlan,
    *,
    memory_eligible: bool = True,
) -> TurnDecision:
    """Bind a proposal to host-owned scopes and degrade violations to No-op."""
    try:
        return _bind(frame, proposal, memory_eligible=memory_eligible)
    except ValidationError:
        noop = DecisionPlan(
            plan_id=PlanId(f"scope-noop-{proposal.turn_id}"),
            turn_id=proposal.turn_id,
            frame_id=proposal.frame_id,
            context_revision=proposal.context_revision,
            capability_revision=proposal.capability_revision,
            created_at=proposal.created_at,
            deadline=proposal.deadline,
            cause_event_ids=proposal.cause_event_ids,
            intents=(
                NoOpIntent(
                    type="noop",
                    intent_id=IntentId(f"scope-noop-intent-{proposal.turn_id}"),
                    cause_event_ids=proposal.cause_event_ids,
                    dependency_ids=(),
                    deadline=proposal.deadline,
                    cancel_policy=CancelPolicy.IF_NOT_STARTED,
                    reason="response_scope_violation",
                ),
            ),
        )
        return _bind(frame, noop, memory_eligible=memory_eligible)


def _bind(
    frame: TurnFrame,
    plan: DecisionPlan,
    *,
    memory_eligible: bool = True,
) -> TurnDecision:
    if plan.frame_id != frame.frame_id:
        raise ValueError("decision frame does not match admitted turn")
    return TurnDecision(
        source_domain=frame.source_domain,
        interaction_scope=frame.interaction_scope,
        response_scope=frame.response_scope,
        plan=plan,
        memory_eligible=memory_eligible,
    )


__all__ = ("govern_decision",)
