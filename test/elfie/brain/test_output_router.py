"""Behavioral tests for atomic multi-intent output routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Event, Lock
from typing import Tuple, TypedDict

from elfie.brain.context_types import (
    BodyCapabilityDescriptor,
    ConnectedChannelDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.decision_types import (
    CancelPolicy,
    DecisionIntent,
    DecisionPlan,
    ExpressionIntent,
    MessageIntent,
    MotionIntent,
    SpeechIntent,
    TurnDecision,
)
from elfie.brain.output_router import OutputRouter
from elfie.brain.output_types import (
    ExecutionBatch,
    IntentExecutionResult,
)
from elfie.brain.perception_types import (
    CommunicationScope,
    EmbodiedScope,
    ExecutionStatus,
    ExternalExecutionDomain,
    ResponseScope,
    SourceDomain,
)
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.message_types import (
    ElfieId,
    EventId,
    IntentId,
    PlanId,
    TurnId,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
DEADLINE = NOW + timedelta(seconds=10)
ELFIE_ID = ElfieId("elfie-router")


class IntentBase(TypedDict):
    intent_id: IntentId
    cause_event_ids: Tuple[EventId, ...]
    dependency_ids: Tuple[IntentId, ...]
    deadline: datetime
    cancel_policy: CancelPolicy


class StaticCapabilities:
    def __init__(self, capabilities: EffectiveCapabilities) -> None:
        self.value = capabilities

    def current(self) -> EffectiveCapabilities:
        return self.value


class RecordingExecutor:
    def __init__(self, *, result: IntentExecutionResult | None = None) -> None:
        self.calls: list[IntentId] = []
        self.interrupts: list[tuple[TurnId, IntentId, str]] = []
        self.result = result or IntentExecutionResult.completed()

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        del plan
        self.calls.append(intent.intent_id)
        return self.result

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        self.interrupts.append((turn_id, intent_id, reason))


class BlockingBodyExecutor(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._active = 0
        self.two_started = Event()
        self.release = Event()

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        del plan
        with self._lock:
            self.calls.append(intent.intent_id)
            self._active += 1
            if self._active >= 2:
                self.two_started.set()
        self.release.wait()
        return IntentExecutionResult.completed()


def _capabilities(*, revision: int = 7) -> EffectiveCapabilities:
    return EffectiveCapabilities(
        revision=revision,
        captured_at=NOW,
        current_body=BodyCapabilityDescriptor(
            body_id="body-1",
            capability_revision=revision,
            sensors=(),
            actions=("speech.say", "walk", "expression.happy"),
        ),
        connected_channels=(
            ConnectedChannelDescriptor(
                channel_id="chat",
                account_id="elfie-account",
                capability_revision=revision,
                content_kinds=("text",),
                authorized_conversation_ids=("conversation-1",),
            ),
        ),
    )


def _base(intent_id: str) -> IntentBase:
    return {
        "intent_id": IntentId(intent_id),
        "cause_event_ids": (EventId("cause-1"),),
        "dependency_ids": (),
        "deadline": DEADLINE,
        "cancel_policy": CancelPolicy.IF_NOT_STARTED,
    }


def _message(index: int) -> MessageIntent:
    return MessageIntent(
        type="message",
        **_base(f"message-{index}"),
        channel_id="chat",
        conversation_id="conversation-1",
        content=f"reply {index}",
        sequence_id="reply-sequence",
        ordinal=index,
        send_after=NOW,
    )


def _plan(intents: tuple[DecisionIntent, ...], *, revision: int = 7) -> DecisionPlan:
    return DecisionPlan(
        plan_id=PlanId("plan-router"),
        turn_id=TurnId("turn-router"),
        frame_id=EventId("frame-router"),
        context_revision=3,
        capability_revision=revision,
        created_at=NOW,
        deadline=DEADLINE,
        cause_event_ids=(EventId("cause-1"),),
        intents=intents,
    )


def _embodied_decision(plan: DecisionPlan) -> TurnDecision:
    return TurnDecision(
        source_domain=SourceDomain.EMBODIED,
        interaction_scope=EmbodiedScope(body_id="body-1"),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.NERVOUS_SYSTEM,
            body_id="body-1",
        ),
        plan=plan,
    )


def _communication_decision(plan: DecisionPlan) -> TurnDecision:
    return TurnDecision(
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="chat",
            conversation_id="conversation-1",
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="chat",
            conversation_id="conversation-1",
        ),
        plan=plan,
    )


def test_embodied_plan_executes_physical_targets_concurrently() -> None:
    # Given: three physical intents in one embodied turn.
    body = BlockingBodyExecutor()
    message = RecordingExecutor()
    internal = RecordingExecutor()
    workspace = PerceptualWorkspace(ELFIE_ID)
    router = OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities()),
        perception_sink=workspace,
        body_executor=body,
        message_executor=message,
        internal_executor=internal,
        clock=lambda: NOW,
    )
    router.start()
    physical: tuple[DecisionIntent, ...] = (
        SpeechIntent(type="speech", text="hello", **_base("speech")),
        MotionIntent(type="motion", motion="walk", **_base("motion")),
        ExpressionIntent(
            type="expression", expression="happy", intensity=0.8, **_base("expression")
        ),
    )

    # When: the complete plan is accepted without blocking the caller.
    batch = router.submit(_embodied_decision(_plan(physical)))
    assert isinstance(batch, ExecutionBatch)
    assert body.two_started.wait(1)
    body.release.set()
    router.wait_for_turn(TurnId("turn-router"), timeout=1)

    # Then: physical work overlapped and the communication executor stayed idle.
    assert message.calls == []
    receipts = router.receipts(TurnId("turn-router"))
    assert len(receipts) == 9
    assert {receipt.turn_id for receipt in receipts} == {TurnId("turn-router")}
    assert {receipt.plan_id for receipt in receipts} == {PlanId("plan-router")}
    assert workspace.metrics().reliable_event_count == 9
    for intent_id in batch.intent_ids:
        assert [
            receipt.status for receipt in receipts if receipt.intent_id == intent_id
        ] == [
            ExecutionStatus.ACCEPTED,
            ExecutionStatus.STARTED,
            ExecutionStatus.COMPLETED,
        ]
    router.stop()
    router.join()


def test_atomic_validation_rejects_stale_capabilities_without_executor_calls() -> None:
    # Given: a plan compiled against an old capability revision.
    body = RecordingExecutor()
    message = RecordingExecutor()
    internal = RecordingExecutor()
    router = OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities(revision=8)),
        perception_sink=PerceptualWorkspace(ELFIE_ID),
        body_executor=body,
        message_executor=message,
        internal_executor=internal,
        clock=lambda: NOW,
    )
    router.start()

    # When: the router evaluates the whole plan before queueing any intent.
    accepted = router.accept(
        _communication_decision(_plan((_message(0),), revision=7))
    )

    # Then: nothing reaches an executor and the rejection is observable.
    assert accepted is False
    assert body.calls == []
    assert message.calls == []
    assert router.last_rejection is not None
    assert router.last_rejection.error.code == "stale_capability_revision"
    router.stop()
    router.join()


def test_repeated_plan_id_returns_same_batch_without_duplicate_execution() -> None:
    # Given: one accepted message plan with a stable idempotency identity.
    message = RecordingExecutor()
    router = OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=StaticCapabilities(_capabilities()),
        perception_sink=PerceptualWorkspace(ELFIE_ID),
        body_executor=RecordingExecutor(),
        message_executor=message,
        internal_executor=RecordingExecutor(),
        clock=lambda: NOW,
    )
    router.start()
    plan = _plan((_message(0),))

    # When: the same complete plan is submitted twice.
    decision = _communication_decision(plan)
    first = router.submit(decision)
    second = router.submit(decision)
    router.wait_for_turn(plan.turn_id, timeout=1)

    # Then: both calls identify one batch and execute the intent exactly once.
    assert isinstance(first, ExecutionBatch)
    assert second == first
    assert message.calls == [IntentId("message-0")]
    assert len(router.receipts(plan.turn_id)) == 3
    router.stop()
    router.join()
