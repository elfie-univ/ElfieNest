"""End-to-end concurrency tests for the single-owner BrainCoordinator."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from threading import Event

from elfie.brain.context_types import (
    ConversationContext,
    EffectiveCapabilities,
    MemoryContext,
)
from elfie.brain.coordinator import BrainCoordinator
from elfie.brain.cortical_worker import CorticalWorker
from elfie.brain.decision_decoder import DecisionPlanDecoder
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.limbic_appraiser import BrainClockPulse, LimbicAppraiser
from elfie.brain.perception_types import (
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    SocialPayload,
)
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.runtime_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelPort,
    StructuredOutputMode,
)
from elfie.brain.turn_outcome import TerminalStatus
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


def _social(index: int, milliseconds: int) -> PerceptionEvent:
    at = NOW + timedelta(milliseconds=milliseconds)
    actor = ActorRef(actor_id=ActorId("owner-1"), source_kind="human")
    return PerceptionEvent(
        meta=_meta(f"social-{index}", at),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="conversation-1",
            sender=actor,
            content=f"message {index}",
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
            items=(),
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
    workspace: PerceptualWorkspace,
    runtime: ModelPort,
    sink: RecordingPlanSink,
    *,
    next_autonomous_at: float | None = None,
) -> tuple[BrainCoordinator, EmotionSystem, HypothalamusEnergy]:
    initial = NOW.timestamp()
    emotion = EmotionSystem(clock=lambda: initial)
    energy = HypothalamusEnergy(clock=lambda: initial)
    worker = CorticalWorker(model_port=runtime, decoder=DecisionPlanDecoder())
    coordinator = BrainCoordinator(
        elfie_id=ELFIE_ID,
        workspace=workspace,
        emotion=emotion,
        homeostasis=energy,
        appraiser=LimbicAppraiser(),
        context_source=EmptyContextSource(),
        cortical_worker=worker,
        plan_sink=sink,
        initial_timestamp=initial,
        next_autonomous_at=next_autonomous_at,
    )
    return coordinator, emotion, energy


def test_slow_runtime_does_not_block_clock_or_next_frame_ingest() -> None:
    # Given: five social messages form one quiet-window turn.
    workspace = PerceptualWorkspace(ELFIE_ID)
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


def test_model_unavailable_is_not_reported_as_a_successful_turn() -> None:
    class UnavailableRuntime:
        def capabilities(self):
            raise RuntimeError("provider unavailable")

        def abandon(self, request):
            del request

        def generate(self, request):
            del request
            raise AssertionError("generation must not start")

    workspace = PerceptualWorkspace(ELFIE_ID)
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
