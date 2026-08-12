"""Host-owned trust binding for model-produced decision plans."""

from __future__ import annotations

from elfie.brain.reasoning.decision_seed import DecisionDecodeSeed
from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionIntent,
    DecisionPlan,
    ExpressionIntent,
    MotionIntent,
    SpeechIntent,
)
from elfie.message_types import PlanId


def bind_plan_to_seed(plan: DecisionPlan, seed: DecisionDecodeSeed) -> DecisionPlan:
    """Replace every security-sensitive envelope field with host-owned values."""
    intents = tuple(_bind_intent(intent, seed) for intent in plan.intents)
    rebound = plan.model_copy(
        update={
            "plan_id": PlanId(f"plan-{seed.turn_id}"),
            "turn_id": seed.turn_id,
            "frame_id": seed.frame_id,
            "context_revision": seed.context_revision,
            "capability_revision": seed.capability_revision,
            "created_at": seed.created_at,
            "deadline": seed.deadline,
            "cause_event_ids": seed.cause_event_ids,
            "intents": intents,
        }
    )
    return DecisionPlan.model_validate(rebound.model_dump(mode="python"))


def _bind_intent(
    intent: DecisionIntent,
    seed: DecisionDecodeSeed,
) -> DecisionIntent:
    return intent.model_copy(
        update={
            "cause_event_ids": seed.cause_event_ids,
            "deadline": seed.deadline,
            "cancel_policy": _trusted_cancel_policy(intent),
        }
    )


def _trusted_cancel_policy(intent: DecisionIntent) -> CancelPolicy:
    if isinstance(
        intent,
        (SpeechIntent, MotionIntent, ExpressionIntent),
    ):
        return CancelPolicy.ALWAYS
    return CancelPolicy.IF_NOT_STARTED


__all__ = ("bind_plan_to_seed",)
