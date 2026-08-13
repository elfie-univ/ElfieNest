from datetime import datetime, timedelta, timezone

from devtools.elfie_lab.turn_projection import project_decision
from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionPlan,
    ExpressionIntent,
    MotionIntent,
    SpeechIntent,
)
from elfie.brain.reasoning.execution_types import ExecutionReceipt, ExecutorKind
from elfie.brain.workspace.contracts import ExecutionStatus
from elfie.message_types import EventId, IntentId, PlanId, TurnId


def test_projects_typed_intents_and_correlates_latest_receipt_status():
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(seconds=10)
    cause_id = EventId("event-1")
    base = {
        "cause_event_ids": (cause_id,),
        "dependency_ids": (),
        "deadline": deadline,
        "cancel_policy": CancelPolicy.IF_NOT_STARTED,
    }
    plan = DecisionPlan(
        plan_id=PlanId("plan-1"),
        turn_id=TurnId("turn-1"),
        frame_id=EventId("frame-1"),
        context_revision=1,
        capability_revision=1,
        created_at=now,
        deadline=deadline,
        cause_event_ids=(cause_id,),
        intents=(
            SpeechIntent(
                type="speech", intent_id=IntentId("speech-1"), text="你好", **base
            ),
            MotionIntent(
                type="motion",
                intent_id=IntentId("motion-1"),
                motion="nod_head",
                **base,
            ),
            ExpressionIntent(
                type="expression",
                intent_id=IntentId("expression-1"),
                expression="happy",
                intensity=0.8,
                **base,
            ),
        ),
    )
    receipts = (
        _receipt(now, "receipt-1", "motion-1", ExecutionStatus.ACCEPTED),
        _receipt(now, "receipt-2", "motion-1", ExecutionStatus.COMPLETED),
        _receipt(now, "receipt-3", "expression-1", ExecutionStatus.COMPLETED),
    )

    projection = project_decision(plan, receipts)

    assert projection["spoken_texts"] == ["你好"]
    assert projection["message_texts"] == []
    assert projection["motion_intents"] == [
        {
            "intent_id": "motion-1",
            "motion": "nod_head",
            "target": None,
            "status": "completed",
            "receipts": ["accepted", "completed"],
        }
    ]
    assert projection["expression_intents"][0]["expression"] == "happy"
    assert projection["expression_intents"][0]["status"] == "completed"
    assert [item["type"] for item in projection["action_intents"]] == [
        "motion",
        "expression",
    ]


def test_missing_plan_projects_to_empty_backward_compatible_contract():
    projection = project_decision(None, ())

    assert projection["plan_id"] is None
    assert projection["spoken_texts"] == []
    assert projection["motion_intents"] == []
    assert projection["expression_intents"] == []


def _receipt(
    now: datetime,
    receipt_id: str,
    intent_id: str,
    status: ExecutionStatus,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id=EventId(receipt_id),
        plan_id=PlanId("plan-1"),
        turn_id=TurnId("turn-1"),
        intent_id=IntentId(intent_id),
        executor=ExecutorKind.BODY,
        status=status,
        occurred_at=now,
    )
