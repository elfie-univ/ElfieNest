"""End-to-end concurrency tests for the single-owner BrainCoordinator."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import MagicMock

import pytest

from elfie.brain.emotion.appraiser import BrainClockPulse, EmotionAppraiser
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.memory.contracts import MemoryContext
from elfie.brain.reasoning.context_types import (
    ConversationContext,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.coordinator import BrainCoordinator
from elfie.brain.reasoning.decision_decoder import DecisionPlanDecoder
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelPort,
    ModelResponseMode,
    StructuredOutputMode,
)
from elfie.brain.reasoning.run import ReasoningRunResult
from elfie.brain.reasoning.turn_outcome import TerminalStatus
from elfie.brain.reasoning.worker import ReasoningWorker
from elfie.brain.workspace.contracts import (
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    SocialPayload,
)
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    Priority,
    TraceId,
    TurnId,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-coordinator")


class NoopSettlement:
    def settle(self, candidates):
        del candidates
        return ()


def _meta(
    event_id: str,
    occurred_at: datetime,
    *,
    priority: Priority = Priority.NORMAL,
) -> MessageMeta:
    return MessageMeta(
        event_id=EventId(event_id),
        elfie_id=ELFIE_ID,
        source=ActorRef(actor_id=ActorId("owner-1"), source_kind="human"),
        occurred_at=occurred_at,
        received_at=occurred_at,
        trace_id=TraceId("trace-coordinator"),
        priority=priority,
    )


def _social(
    index: int,
    milliseconds: int,
    *,
    source_kind: str = "human",
    text: str | None = None,
) -> PerceptionEvent:
    at = NOW + timedelta(milliseconds=milliseconds)
    actor = ActorRef(actor_id=ActorId("owner-1"), source_kind=source_kind)
    return PerceptionEvent(
        meta=_meta(f"social-{index}", at),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="conversation-1",
            sender=actor,
            content=text or f"message {index}",
        ),
        salience=0.5,
    )


def _physical(
    index: int,
    milliseconds: int,
    *,
    salience: float = 0.5,
    priority: Priority = Priority.NORMAL,
) -> PerceptionEvent:
    at = NOW + timedelta(milliseconds=milliseconds)
    return PerceptionEvent(
        meta=_meta(f"physical-{index}", at, priority=priority),
        payload=PhysicalPayload(
            type="physical",
            body_id="body-1",
            modality=PhysicalModality.TOUCH,
            content=f"touch {index}",
        ),
        salience=salience,
    )


class EmptyContextSource:
    def conversation(self, frame, captured_at):
        return ConversationContext(
            revision=frame.revision,
            captured_at=captured_at,
            conversation_id=None,
            messages=(),
        )

    def memory(self, frame, emotion, captured_at):
        return MemoryContext(
            revision=frame.revision,
            captured_at=captured_at,
        )

    def capabilities(self, captured_at):
        return EffectiveCapabilities(
            revision=1,
            captured_at=captured_at,
            current_body=None,
            connected_channels=(),
        )


class RecordingPlanSink:
    def __init__(self) -> None:
        self.plans = []
        self.cancelled: list[tuple[TurnId, str]] = []
        self.accepted = Event()
        self.cancel_seen = Event()

    def accept(self, plan) -> bool:
        self.plans.append(plan)
        self.accepted.set()
        return True

    def cancel_stale(self, turn_id: TurnId, reason: str) -> None:
        self.cancelled.append((turn_id, reason))
        self.cancel_seen.set()


class BlockingPlanRuntime:
    def __init__(self) -> None:
        self.release = Event()
        self.started = Event()
        self.second_started = Event()
        self.calls: list[ModelGenerationRequest] = []

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="fake",
            model_key="fake/schema",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.calls.append(request)
        self.started.set()
        if len(self.calls) == 2:
            self.second_started.set()
        self.release.wait()
        intent_id = f"speech-{request.turn_id}"
        text = json.dumps(
            {
                "schema_version": 1,
                "plan_id": f"plan-{request.turn_id}",
                "turn_id": str(request.turn_id),
                "frame_id": str(request.frame_id),
                "context_revision": request.context_revision,
                "capability_revision": request.capability_revision,
                "created_at": request.created_at.isoformat(),
                "deadline": request.deadline.isoformat(),
                "cause_event_ids": list(request.cause_event_ids),
                "intents": [
                    {
                        "type": "speech",
                        "intent_id": intent_id,
                        "cause_event_ids": list(request.cause_event_ids),
                        "dependency_ids": [],
                        "deadline": request.deadline.isoformat(),
                        "cancel_policy": "if_not_started",
                        "text": "hello",
                    }
                ],
            }
        )
        return ModelGenerationResult(
            text=text,
            selected_mode=StructuredOutputMode.JSON_SCHEMA,
            provider="fake",
            model_key="fake/schema",
        )


def _coordinator(
    workspace: EventWorkspace,
    runtime: ModelPort,
    sink: RecordingPlanSink,
    *,
    next_autonomous_at: float | None = None,
    allowed_tools: tuple[str, ...] = (),
    initial_energy: float = 100.0,
    reasoning_retention: int = 256,
) -> tuple[BrainCoordinator, EmotionSystem, EnergySystem]:
    initial = NOW.timestamp()
    emotion = EmotionSystem(clock=lambda: initial)
    energy = EnergySystem(
        {"limits": {"energy": {"initial_value": initial_energy}}},
        clock=lambda: initial,
    )
    worker = ReasoningWorker(model_port=runtime, decoder=DecisionPlanDecoder())
    coordinator = BrainCoordinator(
        elfie_id=ELFIE_ID,
        workspace=workspace,
        emotion=emotion,
        homeostasis=energy,
        appraiser=EmotionAppraiser(),
        context_source=EmptyContextSource(),
        reasoning_worker=worker,
        plan_sink=sink,
        settlement=NoopSettlement(),
        initial_timestamp=initial,
        next_autonomous_at=next_autonomous_at,
        allowed_tools=allowed_tools,
        reasoning_retention=reasoning_retention,
    )
    return coordinator, emotion, energy


def test_completed_reasoning_traces_have_a_bounded_in_memory_retention() -> None:
    coordinator, _emotion, _energy = _coordinator(
        EventWorkspace(ELFIE_ID),
        BlockingPlanRuntime(),
        RecordingPlanSink(),
        reasoning_retention=2,
    )
    first = MagicMock(spec=ReasoningRunResult)
    second = MagicMock(spec=ReasoningRunResult)
    third = MagicMock(spec=ReasoningRunResult)

    coordinator._remember_reasoning(TurnId("turn-1"), first)
    coordinator._remember_reasoning(TurnId("turn-2"), second)
    coordinator._remember_reasoning(TurnId("turn-3"), third)

    assert coordinator.reasoning(TurnId("turn-1")) is None
    assert coordinator.reasoning(TurnId("turn-2")) is second
    assert coordinator.reasoning(TurnId("turn-3")) is third
    assert coordinator.evicted_reasoning_count == 1


def test_owner_conversation_stays_fast_when_energy_allows_long_reasoning() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        runtime,
        sink,
        allowed_tools=("web_search",),
    )
    coordinator.start()
    workspace.publish(
        _social(
            1,
            0,
            source_kind="owner",
            text="我记得昨天在花园散步",
        )
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        request = runtime.calls[0]
        assert request.reasoning_mode == "fast"
        assert request.response_mode is ModelResponseMode.DIRECT_REPLY
        assert request.allowed_tools == ()
        assert request.max_tokens == 192
        assert len(request.user_prompt) < 2000
        assert "CURRENT_MESSAGE" in request.user_prompt
        assert coordinator._inflight is not None
        assert coordinator._inflight.task.reasoning_budget.max_model_calls == 1
        assert coordinator._inflight.task.reasoning_budget.max_tool_calls == 0
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


@pytest.mark.parametrize(
    "owner_text",
    (
        "明天上午九点提醒我带钥匙",
        "请你比较这三个模型并整理一份报告",
    ),
)
def test_explicit_task_uses_structured_activity_route_without_tools(
    owner_text: str,
) -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        runtime,
        sink,
        allowed_tools=("web_search",),
    )
    coordinator.start()
    workspace.publish(
        _social(
            1,
            0,
            source_kind="owner",
            text=owner_text,
        )
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        request = runtime.calls[0]
        assert request.reasoning_mode == "fast"
        assert request.response_mode is ModelResponseMode.DECISION_PLAN
        assert request.allowed_tools == ()
        assert "PERSISTENT_ACTIVITY" in request.system_prompt
        assert owner_text in request.user_prompt
        assert request.user_prompt.count(owner_text) == 1
        assert request.max_tokens >= 1024
        assert coordinator._inflight is not None
        assert coordinator._inflight.task.reasoning_budget.max_model_calls == 2
        assert coordinator._inflight.task.reasoning_budget.max_tool_calls == 0
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_owner_conversation_still_gets_one_fast_turn_when_energy_is_exhausted() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, energy = _coordinator(
        workspace,
        runtime,
        sink,
        initial_energy=5.0,
    )
    energy.emergency_reserve = 0.0
    coordinator.start()
    workspace.publish(_social(1, 0, source_kind="owner"))
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        request = runtime.calls[0]
        assert request.reasoning_mode == "fast"
        assert request.allowed_tools == ()
        assert coordinator._inflight is not None
        assert coordinator._inflight.task.energy_reservation.source == "responsive"
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_empty_frame_race_does_not_stop_the_brain_owner_thread() -> None:
    class PhantomMetricsWorkspace(EventWorkspace):
        def metrics(self):
            return (
                super()
                .metrics()
                .model_copy(
                    update={
                        "latest_ingest_seq": 1,
                        "reliable_event_count": 1,
                        "critical_event_count": 1,
                        "max_salience": 1.0,
                    }
                )
            )

    workspace = PhantomMetricsWorkspace(ELFIE_ID)
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        BlockingPlanRuntime(),
        RecordingPlanSink(),
    )
    coordinator.start()
    coordinator.notify_perception()
    coordinator.synchronize()

    try:
        assert coordinator.is_alive
        assert coordinator.outcomes() == ()
    finally:
        coordinator.stop()
        coordinator.join()


def test_internal_turn_uses_long_reasoning_only_when_energy_allows_it() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        runtime,
        sink,
        next_autonomous_at=NOW.timestamp(),
        allowed_tools=("web_search",),
    )
    coordinator.start()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp()))
    assert runtime.started.wait(1)
    coordinator.synchronize()

    try:
        request = runtime.calls[0]
        assert request.reasoning_mode == "long"
        assert request.allowed_tools == ("web_search",)
        assert coordinator._inflight is not None
        assert coordinator._inflight.task.reasoning_budget.max_model_calls == 4
        assert coordinator._inflight.task.reasoning_budget.max_tool_calls == 2
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_internal_turn_stays_fast_when_energy_denies_long_reasoning() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        runtime,
        sink,
        next_autonomous_at=NOW.timestamp(),
        allowed_tools=("web_search",),
        initial_energy=50.0,
    )
    coordinator.start()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp()))
    assert runtime.started.wait(1)
    coordinator.synchronize()

    try:
        request = runtime.calls[0]
        assert request.reasoning_mode == "fast"
        assert request.allowed_tools == ()
        assert coordinator._inflight is not None
        assert coordinator._inflight.task.reasoning_budget.max_model_calls == 1
        assert coordinator._inflight.task.reasoning_budget.max_tool_calls == 0
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_slow_runtime_does_not_block_clock_or_next_frame_ingest() -> None:
    # Given: five social messages form one quiet-window turn.
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, emotion, energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    for index in range(5):
        workspace.publish(_social(index, index * 75))
        coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.7))
    runtime.started.wait()
    assert len(runtime.calls) == 1

    # When: 100 body events and another clock pulse arrive during generation.
    for index in range(100):
        workspace.publish(_physical(index, 800))
        coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 1.0))
    coordinator.synchronize()

    # Then: state clocks advance and no second turn starts.
    assert emotion.last_updated_at == NOW.timestamp() + 1.0
    assert energy.last_updated_at == NOW.timestamp() + 1.0
    assert len(runtime.calls) == 1
    runtime.release.set()
    sink.accepted.wait()
    coordinator.synchronize()
    assert workspace.metrics().reliable_event_count == 100
    assert coordinator.outcomes()[0].status is TerminalStatus.COMPLETED
    coordinator.stop()
    coordinator.stop()
    coordinator.join()
    coordinator.join()
    assert coordinator.is_alive is False


def test_perception_arriving_during_a_turn_starts_after_completion() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _, _ = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_social(1, 0, source_kind="owner"))
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1)

    # The second message is ingested while the first provider call owns the
    # logical slot. Its wake-up is coalesced, so completion must re-check it.
    workspace.publish(_social(2, 100, source_kind="owner"))
    coordinator.notify_perception()
    runtime.release.set()

    try:
        coordinator.wait_for_outcome_count(2, timeout=2.0)
        coordinator.synchronize()
        assert len(runtime.calls) == 2
        assert runtime.second_started.is_set()
        assert tuple(outcome.status for outcome in coordinator.outcomes()) == (
            TerminalStatus.COMPLETED,
            TerminalStatus.COMPLETED,
        )
        assert workspace.metrics().reliable_event_count == 0
    finally:
        coordinator.stop()
        coordinator.join()


def test_model_unavailable_is_not_reported_as_a_successful_turn() -> None:
    class UnavailableRuntime:
        def capabilities(self):
            raise RuntimeError("provider unavailable")

        def abandon(self, request):
            del request

        def generate(self, request):
            del request
            raise AssertionError("generation must not start")

    workspace = EventWorkspace(ELFIE_ID)
    sink = RecordingPlanSink()
    coordinator, _, _ = _coordinator(workspace, UnavailableRuntime(), sink)
    coordinator.start()
    workspace.publish(_physical(1, 0, salience=0.95))
    coordinator.notify_perception()
    coordinator.wait_for_outcome()
    coordinator.synchronize()

    outcome = coordinator.outcomes()[0]
    assert outcome.status is TerminalStatus.FAILED
    assert outcome.error_code == "model_unavailable:RuntimeError"
    assert tuple(intent.type for intent in sink.plans[0].plan.intents) == ("noop",)
    coordinator.stop()
    coordinator.join()
