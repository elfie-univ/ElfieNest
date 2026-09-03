"""Deterministic tests for the single-domain response boundary."""

from elfie.brain.reasoning.decision_governance import govern_decision
from elfie.brain.reasoning.decision_types import CapabilityIntent, NoOpIntent
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    ResponseScope,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import EventId
from test.elfie.brain.reasoning.test_output_router import NOW, _base, _message, _plan


def _communication_frame() -> TurnFrame:
    return TurnFrame(
        frame_id=EventId("frame-router"),
        elfie_id="elfie-router",
        revision=1,
        captured_at=NOW,
        cutoff_seq=1,
        trigger_reason=TriggerReason.MANUAL,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="chat", conversation_id="conversation-1"
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="chat",
            conversation_id="conversation-1",
        ),
    )


def test_communication_turn_rejects_body_motion_before_output_router() -> None:
    proposal = _plan(
        (
            CapabilityIntent(
                type="capability",
                category="body",
                capability_id="move.forward",
                arguments={"distance": 1.0},
                **_base("motion"),
            ),
        )
    )

    decision = govern_decision(_communication_frame(), proposal)

    assert len(decision.plan.intents) == 1
    assert isinstance(decision.plan.intents[0], NoOpIntent)
    assert decision.plan.intents[0].reason == "response_scope_violation"


def test_communication_turn_keeps_reply_in_the_admitted_conversation() -> None:
    proposal = _plan((_message(0),))

    decision = govern_decision(_communication_frame(), proposal)

    assert decision.plan == proposal
    assert decision.response_scope.conversation_id == "conversation-1"
