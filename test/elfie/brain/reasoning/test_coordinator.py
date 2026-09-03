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
from elfie.brain.memory.memory_records import RecallBundle
from elfie.brain.reasoning.context_types import (
    BodyCapabilityDescriptor,
    CapabilityDescriptor,
    ConversationContext,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.coordinator import BrainCoordinator
from elfie.brain.reasoning.decision_decoder import DecisionPlanDecoder
from elfie.brain.reasoning.embodied_control import EmbodiedInputMode
from elfie.brain.reasoning.memory_context import (
    MemoryRecallResult,
    ReasoningMemoryTurn,
)
from elfie.brain.reasoning.model_header import ReasoningConstitution
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
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from elfie.brain.workspace.contracts import (
    ExecutionPayload,
    ExecutionStatus,
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    SocialPayload,
    TriggerReason,
)
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    IntentId,
    MessageMeta,
    PlanId,
    Priority,
    TraceId,
    TurnId,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_reasoning_constitution,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-coordinator")


class NoopSettlement:
    def settle(self, candidates):
        del candidates
        return ()

    def capture_episodes(self, episodes):
        del episodes
        return ()


def _meta(
    event_id: str,
    occurred_at: datetime,
    *,
    priority: Priority = Priority.NORMAL,
    causation_id: str | None = None,
) -> MessageMeta:
    return MessageMeta(
        event_id=EventId(event_id),
        elfie_id=ELFIE_ID,
        source=ActorRef(actor_id=ActorId("owner-1"), source_kind="human"),
        occurred_at=occurred_at,
        received_at=occurred_at,
        trace_id=TraceId("trace-coordinator"),
        causation_id=EventId(causation_id) if causation_id is not None else None,
        priority=priority,
    )


def _social(
    index: int,
    milliseconds: int,
    *,
    source_kind: str = "human",
    text: str | None = None,
    salience: float = 0.5,
    priority: Priority = Priority.NORMAL,
) -> PerceptionEvent:
    at = NOW + timedelta(milliseconds=milliseconds)
    actor = ActorRef(actor_id=ActorId("owner-1"), source_kind=source_kind)
    return PerceptionEvent(
        meta=_meta(f"social-{index}", at, priority=priority),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="conversation-1",
            sender=actor,
            content=text or f"message {index}",
        ),
        salience=salience,
    )


def _physical(
    index: int,
    milliseconds: int,
    *,
    salience: float = 0.5,
    priority: Priority = Priority.NORMAL,
    causation_id: str | None = None,
) -> PerceptionEvent:
    at = NOW + timedelta(milliseconds=milliseconds)
    return PerceptionEvent(
        meta=_meta(
            f"physical-{index}",
            at,
            priority=priority,
            causation_id=causation_id,
        ),
        payload=PhysicalPayload(
            type="physical",
            body_id="body-1",
            modality=PhysicalModality.TOUCH,
            content=f"touch {index}",
        ),
        salience=salience,
    )


def _receipt(
    index: int,
    *,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    error=None,
) -> PerceptionEvent:
    at = NOW + timedelta(milliseconds=index)
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId(f"receipt-{index}"),
            elfie_id=ELFIE_ID,
            source=ActorRef(
                actor_id=ActorId("elfie-coordinator:output-router"),
                source_kind="internal",
            ),
            occurred_at=at,
            received_at=at,
            trace_id=TraceId("trace-receipt"),
            causation_id=EventId("owner-cause"),
        ),
        payload=ExecutionPayload(
            type="execution",
            receipt_id=EventId(f"receipt-{index}"),
            plan_id=PlanId("plan-owner"),
            turn_id=TurnId("turn-owner"),
            intent_id=IntentId(f"message-{index}"),
            executor="communication",
            status=status,
            error=error,
        ),
        salience=0.8 if error is not None else 0.4,
    )


class EmptyContextSource:
    def flush_pending_handoffs(self, capture):
        del capture
        return ()

    def conversation(self, frame, captured_at):
        return ConversationContext(
            revision=frame.revision,
            captured_at=captured_at,
            conversation_id=None,
            messages=(),
        )

    def memory_turn(self, frame, emotion, captured_at):
        del emotion

        class EmptyMemorySession:
            pinned_revision = 0
            baseline_result = MemoryRecallResult(
                status="skipped",
                query="",
                pinned_revision=0,
                bundle=RecallBundle(),
                reason="test_empty_memory",
            )

            def recall(self, query):
                return MemoryRecallResult(
                    status="skipped",
                    query=query,
                    pinned_revision=0,
                    bundle=RecallBundle(),
                    reason="test_empty_memory",
                )

        return ReasoningMemoryTurn(
            context=MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
            ),
            session=EmptyMemorySession(),
        )

    def capabilities(self, captured_at):
        return EffectiveCapabilities(
            revision=1,
            captured_at=captured_at,
            current_body=None,
            connected_channels=(),
        )

    def selfhood(self, captured_at):
        return SelfhoodPromptProjection(
            revision=1,
            captured_at=captured_at,
            identity_core_text="我是小狐，是 ElfieNest 的居民。",
            adaptive_self_text="我会先观察，再清楚地表达。",
        )


class MockEmbodiedContextSource(EmptyContextSource):
    def capabilities(self, captured_at):
        return EffectiveCapabilities(
            revision=1,
            captured_at=captured_at,
            current_body=BodyCapabilityDescriptor(
                body_id="body-1",
                body_generation=1,
                capability_revision=1,
                sensors=("proprioception",),
                actions=("move_to_anchor",),
            ),
            world_capabilities=("world.go_to",),
            capability_catalog=(
                CapabilityDescriptor(
                    capability_id="world.go_to",
                    category="world",
                    argument_schema={
                        "type": "object",
                        "required": ["anchor_id"],
                        "properties": {
                            "anchor_id": {
                                "type": "string",
                                "enum": ["room/chair", "room/door"],
                            }
                        },
                    },
                ),
            ),
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
        self.feedback: dict[str, object] | None = None

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
        if request.response_schema.name == "CognitiveAction":
            cognitive: dict[str, object] = {
                "type": "answer",
                "content": "hello",
            }
            if self.feedback is not None:
                cognitive["emotion_feedback"] = self.feedback
            return ModelGenerationResult(
                text=json.dumps(cognitive),
                selected_mode=StructuredOutputMode.JSON_SCHEMA,
                provider="fake",
                model_key="fake/schema",
            )
        intent_id = f"speech-{request.turn_id}"
        payload: dict[str, object] = {
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
        if self.feedback is not None:
            payload["emotion_feedback"] = self.feedback
        text = json.dumps(payload)
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
    context_source=None,
    embodied_input_mode: EmbodiedInputMode = EmbodiedInputMode.BRAIN,
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
        context_source=context_source or EmptyContextSource(),
        reasoning_worker=worker,
        plan_sink=sink,
        settlement=NoopSettlement(),
        constitution=ReasoningConstitution.from_mapping(load_reasoning_constitution()),
        initial_timestamp=initial,
        next_autonomous_at=next_autonomous_at,
        embodied_input_mode=embodied_input_mode,
        allowed_tools=allowed_tools,
        reasoning_retention=reasoning_retention,
    )
    return coordinator, emotion, energy


def test_mock_mode_routes_embodied_wander_without_model_inference() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        runtime,
        sink,
        context_source=MockEmbodiedContextSource(),
        embodied_input_mode=EmbodiedInputMode.MOCK,
    )
    coordinator.start()

    try:
        coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 1.0))
        assert sink.accepted.wait(1), coordinator.outcomes()
        assert runtime.calls == []
        assert len(sink.plans) == 1
        assert sink.plans[0].plan.intents[0].capability_id == "world.go_to"
    finally:
        coordinator.stop()
        coordinator.join()


def test_mock_mode_keeps_communication_on_the_model_path() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        runtime,
        sink,
        context_source=MockEmbodiedContextSource(),
        embodied_input_mode=EmbodiedInputMode.MOCK,
    )
    coordinator.start()

    try:
        workspace.publish(_social(1, 0, source_kind="owner"))
        coordinator.notify_perception()
        coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
        assert runtime.started.wait(1), coordinator.outcomes()
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()

    assert len(runtime.calls) == 1


def test_routine_receipts_bypass_model_but_failed_receipts_remain_eligible() -> None:
    routine_workspace = EventWorkspace(ELFIE_ID)
    for index, status in enumerate(
        (
            ExecutionStatus.ACCEPTED,
            ExecutionStatus.STARTED,
            ExecutionStatus.COMPLETED,
        ),
        start=1,
    ):
        routine_workspace.publish(_receipt(index, status=status))
    routine_frame = routine_workspace.claim_frame(
        routine_workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-receipt-routine"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )

    failed_workspace = EventWorkspace(ELFIE_ID)
    failed_workspace.publish(
        _receipt(4, status=ExecutionStatus.REJECTED),
    )
    failed_frame = failed_workspace.claim_frame(
        failed_workspace.metrics().latest_ingest_seq,
        turn_id=TurnId("turn-receipt-failed"),
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )

    assert BrainCoordinator._requires_model(routine_frame) is False
    assert BrainCoordinator._requires_model(failed_frame) is True


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
        assert request.max_tokens == 1536
        assert len(request.user_prompt) < 2000
        assert "CURRENT_MESSAGE" in request.user_prompt
        assert coordinator._inflight is not None
        assert coordinator._inflight.task.reasoning_budget.max_model_calls == 1
        assert coordinator._inflight.task.reasoning_budget.max_tool_calls == 0
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_embodied_fast_turn_reserves_complete_decision_plan_budget() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _emotion, _energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_physical(1, 0, salience=0.95))
    coordinator.notify_perception()
    assert runtime.started.wait(1), coordinator.outcomes()

    try:
        assert runtime.calls[0].response_mode is ModelResponseMode.DECISION_PLAN
        assert runtime.calls[0].max_tokens == 1024
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_terminal_action_outcome_frame_is_model_admitted_without_new_trigger() -> None:
    event = _physical(1, 0, salience=0.7).model_copy(
        update={
            "payload": PhysicalPayload(
                type="physical",
                body_id="body-1",
                modality=PhysicalModality.PROPRIOCEPTION,
                content="action=command-1; intent=intent-1; status=completed",
            )
        }
    )
    frame = MagicMock(events=(event,))

    assert BrainCoordinator._requires_model(frame) is True


def test_owner_text_affect_cannot_use_an_untrusted_direct_scope() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    runtime.feedback = {
        "appraisals": [
            {
                "scope_id": "appraisal:social-1:direct",
                "effects": [
                    {
                        "channel": "anger",
                        "direction": "increase",
                        "strength": 100,
                        "confidence": 1.0,
                    }
                ],
            }
        ]
    }
    sink = RecordingPlanSink()
    coordinator, emotion, _energy = _coordinator(
        workspace,
        runtime,
        sink,
    )
    coordinator.start()
    workspace.publish(
        _social(
            1,
            0,
            source_kind="owner",
            text="I am furious about this",
        )
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        assert (
            emotion.get_emotion_value("anger") == emotion.parameters("anger").baseline
        )
        assert "CURRENT_BRAIN_STATE" in runtime.calls[0].system_prompt
        runtime.release.set()
        assert sink.accepted.wait(1), coordinator.outcomes()
        assert (
            emotion.get_emotion_value("anger") == emotion.parameters("anger").baseline
        )
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_model_emotion_feedback_replaces_provisional_entry_appraisal() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    runtime.feedback = {
        "appraisals": [
            {
                "scope_id": "appraisal:social-1:direct",
                "effects": [
                    {
                        "channel": "happiness",
                        "direction": "increase",
                        "strength": 80,
                        "confidence": 1.0,
                    }
                ],
            }
        ]
    }
    sink = RecordingPlanSink()
    coordinator, emotion, _energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(
        _social(
            1,
            0,
            source_kind="owner",
            text="I hate you",
        )
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        assert emotion.get_emotion_value("anger") > emotion.parameters("anger").baseline
        system_prompt = runtime.calls[0].system_prompt
        assert "EMOTION_FEEDBACK" in system_prompt
        assert "elfie emotion: primary=calm" in system_prompt
        assert "anger at" not in system_prompt
        runtime.release.set()
        assert sink.accepted.wait(1), coordinator.outcomes()
        assert emotion.get_emotion_value("anger") == pytest.approx(
            emotion.parameters("anger").baseline
        )
        assert (
            emotion.get_emotion_value("happiness")
            > emotion.parameters("happiness").baseline
        )
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_model_explicit_empty_appraisal_replaces_fast_effect_with_noop() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    runtime.feedback = {"appraisals": []}
    sink = RecordingPlanSink()
    coordinator, emotion, _energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(
        _social(
            1,
            0,
            source_kind="owner",
            text="I hate you",
        )
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        assert emotion.get_emotion_value("anger") > emotion.parameters("anger").baseline
        runtime.release.set()
        assert sink.accepted.wait(1), coordinator.outcomes()
        assert emotion.get_emotion_value("anger") == pytest.approx(
            emotion.parameters("anger").baseline
        )
        assert emotion.get_emotion_value("sadness") == pytest.approx(
            emotion.parameters("sadness").baseline
        )
        assert emotion.get_emotion_value("happiness") == pytest.approx(
            emotion.parameters("happiness").baseline
        )
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_model_decrease_guides_the_same_continuing_cause_on_the_next_frame() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    runtime.feedback = {
        "appraisals": [
            {
                "scope_id": "appraisal:physical-1:direct",
                "effects": [
                    {
                        "channel": "fear",
                        "direction": "decrease",
                        "strength": 100,
                        "confidence": 1.0,
                    }
                ],
            }
        ]
    }
    sink = RecordingPlanSink()
    coordinator, emotion, _energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(
        _physical(1, 0, salience=0.95, causation_id="continuing-elephant")
    )
    coordinator.notify_perception()
    assert runtime.started.wait(1), coordinator.outcomes()

    try:
        runtime.release.set()
        coordinator.wait_for_outcome_count(1, timeout=2.0)
        workspace.publish(
            _physical(2, 1000, salience=0.5, causation_id="continuing-elephant")
        )
        coordinator.notify_perception()
        coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 7.0))
        coordinator.wait_for_outcome_count(2, timeout=2.0)
        coordinator.synchronize()

        assert len(runtime.calls) == 1
        assert emotion.get_emotion_value("fear") <= emotion.parameters("fear").baseline
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_missing_model_feedback_keeps_the_fast_appraisal() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, emotion, _energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_social(1, 0, source_kind="owner", text="I hate you"))
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1)
    coordinator.synchronize()
    fast_anger = emotion.get_emotion_value("anger")

    try:
        runtime.release.set()
        assert sink.accepted.wait(1), coordinator.outcomes()
        assert emotion.get_emotion_value("anger") == pytest.approx(fast_anger)
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_unknown_model_appraisal_scope_is_ignored_as_untrusted_feedback() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    runtime.feedback = {
        "appraisals": [
            {
                "scope_id": "model-invented-scope",
                "effects": [
                    {
                        "channel": "anger",
                        "direction": "decrease",
                        "strength": 100,
                        "confidence": 1.0,
                    }
                ],
            }
        ]
    }
    sink = RecordingPlanSink()
    coordinator, emotion, _energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_social(1, 0, source_kind="owner", text="I hate you"))
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1)
    coordinator.synchronize()
    fast_anger = emotion.get_emotion_value("anger")

    try:
        runtime.release.set()
        assert sink.accepted.wait(1), coordinator.outcomes()
        assert emotion.get_emotion_value("anger") == pytest.approx(fast_anger)
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_pre_sleep_model_feedback_cannot_mutate_the_new_emotion_epoch() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    runtime.feedback = {
        "appraisals": [
            {
                "scope_id": "appraisal:social-1:direct",
                "effects": [
                    {
                        "channel": "anger",
                        "direction": "increase",
                        "strength": 100,
                        "confidence": 1.0,
                    }
                ],
            }
        ]
    }
    sink = RecordingPlanSink()
    coordinator, emotion, _energy = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_social(1, 0, source_kind="owner", text="I hate you"))
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1)
    coordinator.synchronize()
    emotion.reset_to_baseline(coordinator._timestamp)

    try:
        runtime.release.set()
        assert sink.accepted.wait(1), coordinator.outcomes()
        assert emotion.get_emotion_value("anger") == pytest.approx(
            emotion.parameters("anger").baseline
        )
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_frame_replay_reuses_fast_candidate_without_double_application() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    coordinator, emotion, _energy = _coordinator(
        workspace,
        BlockingPlanRuntime(),
        RecordingPlanSink(),
    )
    workspace.publish(_social(1, 0, source_kind="owner", text="I hate you"))
    first_turn = TurnId("turn-first")
    frame = workspace.claim_frame(
        workspace.metrics().latest_ingest_seq,
        turn_id=first_turn,
        reason=TriggerReason.MANUAL,
        captured_at=NOW,
    )
    txn, is_new = coordinator._prepare_affect_transaction(frame)
    assert is_new is True
    assert emotion.commit_turn_state(txn.fast_candidate)
    coordinator._affect_txn = txn
    first_anger = emotion.get_emotion_value("anger")
    workspace.release(frame.frame_id, first_turn, "test-replay")

    replay_turn = TurnId("turn-replay")
    replay_frame = workspace.claim(frame.frame_id, replay_turn)
    replay_txn, is_new = coordinator._prepare_affect_transaction(replay_frame)

    assert is_new is False
    assert replay_txn is txn
    assert emotion.get_emotion_value("anger") == pytest.approx(first_anger)


@pytest.mark.parametrize("owner_text", ("明天上午九点提醒我带钥匙",))
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
        assert coordinator._inflight.task.reasoning_budget.max_model_calls == 1
        assert coordinator._inflight.task.reasoning_budget.max_tool_calls == 0
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_owner_keywords_do_not_select_deliberate_budget() -> None:
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
            text="请比较这三个模型的优缺点，并解释你的判断。",
        )
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        request = runtime.calls[0]
        assert request.response_mode is ModelResponseMode.DIRECT_REPLY
        assert request.reasoning_mode == "fast"
        assert request.allowed_tools == ()
        assert "[SEARCH]" not in request.system_prompt
        assert "PERSISTENT_ACTIVITY_ROUTING" not in request.system_prompt
        assert coordinator._inflight is not None
        task = coordinator._inflight.task
        assert task.reasoning_depth.value == "direct"
        assert task.reasoning_budget.max_model_calls == 1
        assert task.reasoning_budget.max_tool_calls == 0
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_high_salience_owner_message_selects_deliberate_budget_without_keywords() -> (
    None
):
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
            text="帮我看看这个",
            salience=0.95,
        )
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        request = runtime.calls[0]
        assert request.response_mode is ModelResponseMode.DIRECT_REPLY
        assert request.reasoning_mode == "long"
        assert request.allowed_tools == ()
        assert coordinator._inflight is not None
        task = coordinator._inflight.task
        assert task.reasoning_depth.value == "deliberate"
        assert task.reasoning_budget.max_model_calls == 3
        assert task.reasoning_budget.max_planned_model_calls == 8
        assert task.reasoning_budget.max_steps is None
        assert task.reasoning_budget.max_tool_calls == 0
        assert task.reasoning_budget.deadline_seconds is None
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
        assert request.allowed_tools == ()
        assert coordinator._inflight is not None
        budget = coordinator._inflight.task.reasoning_budget
        assert budget.max_model_calls == 3
        assert budget.max_planned_model_calls == 8
        assert budget.max_steps is None
        assert coordinator._inflight.task.reasoning_budget.max_tool_calls == 2
        assert budget.deadline_seconds is None
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
        workspace.publish(_social(index, index * 75, source_kind="owner"))
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
