"""将生产 DecisionPlan 投影为稳定、可展示的 Lab 回合数据。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, Iterable, List, Optional

from elfie.brain.decision_types import (
    DecisionPlan,
    ExpressionIntent,
    InternalIntent,
    MessageIntent,
    MotionIntent,
    NoOpIntent,
    PersistentActivityIntent,
    SpeechIntent,
)
from elfie.brain.output_types import ExecutionReceipt


def project_decision(
    plan: Optional[DecisionPlan],
    receipts: Iterable[ExecutionReceipt],
) -> Dict[str, Any]:
    """保留 typed intent，并按 intent_id 关联有序执行状态。"""
    projected: Dict[str, Any] = {
        "schema_version": 1,
        "plan_id": None,
        "turn_id": None,
        "spoken_texts": [],
        "message_texts": [],
        "speech_intents": [],
        "message_intents": [],
        "motion_intents": [],
        "expression_intents": [],
        "action_intents": [],
        "internal_intents": [],
        "activity_intents": [],
        "noop_intents": [],
    }
    if plan is None:
        return projected

    receipt_statuses = _receipt_statuses(receipts)
    projected["plan_id"] = str(plan.plan_id)
    projected["turn_id"] = str(plan.turn_id)

    for intent in plan.intents:
        statuses = receipt_statuses.get(str(intent.intent_id), [])
        common: Dict[str, Any] = {
            "intent_id": str(intent.intent_id),
            "status": statuses[-1] if statuses else "pending",
            "receipts": statuses,
        }
        if isinstance(intent, SpeechIntent):
            projected["spoken_texts"].append(intent.text)
            projected["speech_intents"].append({**common, "text": intent.text})
        elif isinstance(intent, MessageIntent):
            projected["message_texts"].append(intent.content)
            projected["message_intents"].append(
                {
                    **common,
                    "channel_id": intent.channel_id,
                    "conversation_id": intent.conversation_id,
                    "content": intent.content,
                }
            )
        elif isinstance(intent, MotionIntent):
            action = {**common, "motion": intent.motion, "target": intent.target}
            projected["motion_intents"].append(action)
            projected["action_intents"].append({"type": "motion", **action})
        elif isinstance(intent, ExpressionIntent):
            action = {
                **common,
                "expression": intent.expression,
                "intensity": intent.intensity,
            }
            projected["expression_intents"].append(action)
            projected["action_intents"].append({"type": "expression", **action})
        elif isinstance(intent, InternalIntent):
            projected["internal_intents"].append(
                {
                    **common,
                    "operation": intent.operation.value,
                    "content": intent.content,
                }
            )
        elif isinstance(intent, PersistentActivityIntent):
            projected["activity_intents"].append(
                {
                    **common,
                    "activity_id": str(intent.draft.activity_id),
                    "goal": intent.draft.goal,
                    "state": "pending",
                    "wake_at": (
                        intent.draft.wake_at.isoformat()
                        if intent.draft.wake_at is not None
                        else None
                    ),
                    "step_count": len(intent.draft.steps),
                }
            )
        elif isinstance(intent, NoOpIntent):
            projected["noop_intents"].append({**common, "reason": intent.reason})
    return projected


def _receipt_statuses(
    receipts: Iterable[ExecutionReceipt],
) -> DefaultDict[str, List[str]]:
    statuses: DefaultDict[str, List[str]] = defaultdict(list)
    for receipt in receipts:
        statuses[str(receipt.intent_id)].append(receipt.status.value)
    return statuses


__all__ = ("project_decision",)
