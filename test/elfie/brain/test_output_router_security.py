"""Security boundaries for model-selected output targets and schedules."""

from __future__ import annotations

from datetime import timedelta

from elfie.brain.decision_types import (
    CancelPolicy,
    DecisionPlan,
    NoOpIntent,
    TurnDecision,
)
from elfie.brain.output_router import OutputRouter
from elfie.brain.perception_types import (
    CommunicationScope,
    ExternalExecutionDomain,
    ResponseScope,
    SourceDomain,
)
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.message_types import EventId, IntentId, PlanId, TurnId
from test.elfie.brain.test_output_router import (
    ELFIE_ID,
    NOW,
    RecordingExecutor,
    StaticCapabilities,
    _capabilities,
    _embodied_decision,
    _message,
    _plan,
)


def _router(message: RecordingExecutor | None = None) -> OutputRouter:
    return OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities()),
        perception_sink=PerceptualWorkspace(ELFIE_ID),
        body_executor=RecordingExecutor(),
        message_executor=message or RecordingExecutor(),
        internal_executor=RecordingExecutor(),
        clock=lambda: NOW,
    )


def test_router_rejects_message_target_without_inbound_authorization() -> None:
    # Given: a connected channel but no trusted inbound conversation for this target.
    message = RecordingExecutor()
    router = _router(message)
    router.start()
    unauthorized = _message(0).model_copy(
        update={"conversation_id": "attacker-selected-recipient"}
    )

    # When: a model-selected recipient has no trusted inbound conversation grant.
    plan = _plan((unauthorized,))
    accepted = router.accept(
        TurnDecision(
            source_domain=SourceDomain.COMMUNICATION,
            interaction_scope=CommunicationScope(
                channel_id="chat",
                conversation_id="attacker-selected-recipient",
            ),
            response_scope=ResponseScope(
                external_domain=ExternalExecutionDomain.COMMUNICATION,
                channel_id="chat",
                conversation_id="attacker-selected-recipient",
            ),
            plan=plan,
        )
    )

    # Then: no platform executor is called.
    assert accepted is False
    assert message.calls == []
    assert router.last_rejection is not None
    assert router.last_rejection.error.code == "conversation_unauthorized"
    router.stop()
    router.join()


def test_router_rejects_plan_beyond_maximum_schedule_horizon() -> None:
    # Given: a structurally valid plan whose deadline is one day away.
    router = _router()
    router.start()
    far_deadline = NOW + timedelta(days=1)
    noop = NoOpIntent(
        type="noop",
        intent_id=IntentId("future-noop"),
        cause_event_ids=(EventId("cause-1"),),
        dependency_ids=(),
        deadline=far_deadline,
        cancel_policy=CancelPolicy.IF_NOT_STARTED,
        reason="wait",
    )
    future_plan = DecisionPlan(
        plan_id=PlanId("future-plan"),
        turn_id=TurnId("future-turn"),
        frame_id=EventId("future-frame"),
        context_revision=3,
        capability_revision=7,
        created_at=NOW,
        deadline=far_deadline,
        cause_event_ids=(EventId("cause-1"),),
        intents=(noop,),
    )

    # When / Then: direct Router callers cannot create unbounded scheduled work.
    assert router.accept(_embodied_decision(future_plan)) is False
    assert router.last_rejection is not None
    assert router.last_rejection.error.code == "schedule_horizon_exceeded"
    router.stop()
    router.join()
