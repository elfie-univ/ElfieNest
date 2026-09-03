"""将生产 DecisionPlan 投影为稳定、可展示的 Lab 回合数据。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, Iterable, List, Optional

from elfie.brain.reasoning.decision_types import (
    CapabilityIntent,
    DecisionPlan,
    MessageIntent,
    NoOpIntent,
    PersistentActivityRequest,
)
from elfie.brain.reasoning.execution_types import ExecutionReceipt


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
        if isinstance(intent, CapabilityIntent):
            _project_capability(projected, common, intent)
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
        elif isinstance(intent, PersistentActivityRequest):
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


def _project_capability(
    projected: Dict[str, Any],
    common: Dict[str, Any],
    intent: CapabilityIntent,
) -> None:
    """Project dynamic capability calls into the stable Lab display groups."""
    capability_id = intent.capability_id
    arguments = dict(intent.arguments)
    if intent.category == "body" and capability_id in {
        "speak",
        "body.speak",
        "speech.say",
    }:
        text = arguments.get("text")
        if isinstance(text, str):
            projected["spoken_texts"].append(text)
            projected["speech_intents"].append({**common, "text": text})
        return
    if capability_id == "expression" or capability_id.startswith("expression."):
        expression = arguments.get("kind")
        if not isinstance(expression, str):
            expression = capability_id.removeprefix("expression.")
        intensity = arguments.get("intensity", 1.0)
        action = {
            **common,
            "expression": expression,
            "intensity": intensity,
            "capability_id": capability_id,
        }
        projected["expression_intents"].append(action)
        projected["action_intents"].append({"type": "expression", **action})
        return
    if capability_id.startswith("move.") or capability_id in {
        "move.to",
        "body.move_to_anchor",
        "move_to_anchor",
    }:
        action = {
            **common,
            "motion": capability_id,
            "target": arguments.get("anchor_id"),
            "capability_id": capability_id,
        }
        projected["motion_intents"].append(action)
        projected["action_intents"].append({"type": "motion", **action})
        return
    projected["action_intents"].append(
        {
            "type": "capability",
            **common,
            "category": intent.category,
            "capability_id": capability_id,
            "arguments": arguments,
        }
    )


def _receipt_statuses(
    receipts: Iterable[ExecutionReceipt],
) -> DefaultDict[str, List[str]]:
    statuses: DefaultDict[str, List[str]] = defaultdict(list)
    for receipt in receipts:
        statuses[str(receipt.intent_id)].append(receipt.status.value)
    return statuses


__all__ = ("project_decision",)
