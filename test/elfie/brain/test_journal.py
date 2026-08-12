"""Causal Brain journal and restart-reconciliation behavior."""

from datetime import datetime, timedelta, timezone

from elfie.brain.journal import (
    BrainJournal,
    BrainJournalKind,
    InMemoryBrainJournal,
    reconciliation_fact_to_perception,
)
from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    DecisionPlan,
    NoOpIntent,
    TurnDecision,
)
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    InternalPayload,
    InternalSignal,
    PerceptionEvent,
    ResponseScope,
    SocialPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    IntentId,
    MessageMeta,
    PlanId,
    TraceId,
    TurnId,
)

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-journal")


def _frame() -> TurnFrame:
    event = PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId("message-1"),
            elfie_id=ELFIE_ID,
            source=ActorRef(actor_id=ActorId("owner"), source_kind="human"),
            occurred_at=NOW,
            received_at=NOW,
            trace_id=TraceId("trace-1"),
        ),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="owner-chat",
            sender=ActorRef(actor_id=ActorId("owner"), source_kind="human"),
            content="hello",
        ),
    )
    return TurnFrame(
        frame_id=EventId("frame-1"),
        elfie_id=ELFIE_ID,
        revision=1,
        captured_at=NOW,
        cutoff_seq=1,
        trigger_reason=TriggerReason.CONVERSATION_QUIET,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        events=(event,),
    )


def _decision() -> TurnDecision:
    plan = DecisionPlan(
        plan_id=PlanId("plan-1"),
        turn_id=TurnId("turn-1"),
        frame_id=EventId("frame-1"),
        context_revision=1,
        capability_revision=1,
        created_at=NOW,
        deadline=NOW + timedelta(seconds=20),
        cause_event_ids=(EventId("message-1"),),
        intents=(
            NoOpIntent(
                type="noop",
                intent_id=IntentId("noop-1"),
                cause_event_ids=(EventId("message-1"),),
                dependency_ids=(),
                deadline=NOW + timedelta(seconds=20),
                cancel_policy=CancelPolicy.IF_NOT_STARTED,
                reason="nothing to do",
            ),
        ),
    )
    return TurnDecision(
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        plan=plan,
    )


def test_restart_closes_unfinished_run_and_directive_without_replay() -> None:
    store = InMemoryBrainJournal()
    journal = BrainJournal(elfie_id=ELFIE_ID, store=store, clock=lambda: NOW)
    journal.record_run_started(_frame(), TurnId("turn-1"))
    journal.record_decision(_decision())

    facts = journal.reconcile_unfinished()

    assert {(fact.subject, fact.turn_id) for fact in facts} == {
        ("run", TurnId("turn-1")),
        ("directive", TurnId("turn-1")),
    }
    assert journal.reconcile_unfinished() == ()
    assert [entry.kind for entry in journal.entries()][-2:] == [
        BrainJournalKind.RUN_RECONCILED,
        BrainJournalKind.DIRECTIVE_RECONCILED,
    ]


def test_reconciliation_fact_reenters_as_inert_internal_failure() -> None:
    store = InMemoryBrainJournal()
    journal = BrainJournal(elfie_id=ELFIE_ID, store=store, clock=lambda: NOW)
    journal.record_run_started(_frame(), TurnId("turn-1"))
    fact = journal.reconcile_unfinished()[0]

    event = reconciliation_fact_to_perception(
        fact,
        elfie_id=ELFIE_ID,
        occurred_at=NOW,
    )

    assert isinstance(event.payload, InternalPayload)
    assert event.payload.signal is InternalSignal.PROCESSING_FAILURE
    assert event.payload.response_scope is None
    assert "turn-1" in event.payload.detail
