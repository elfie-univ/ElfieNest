"""The Context Engine compile emits one typed compiled_context observation."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import List, Tuple

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.memory.contracts import MemoryContext
from elfie.brain.memory.memory_records import RecallBundle
from elfie.brain.observation import BrainObservation, ObservationStatus
from elfie.brain.reasoning.context_types import (
    ConversationContext,
    ConversationMessage,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.coordinator_turn import ReasoningRunController
from elfie.brain.reasoning.memory_context import (
    MemoryRecallResult,
    ReasoningMemoryTurn,
)
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.reasoning.observation_payloads import CompiledContextObservation
from elfie.brain.reasoning.run import CurrentRunObservation
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    PerceptionEvent,
    ResponseScope,
    SocialPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import (
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
    TurnId,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_reasoning_constitution,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-obs")
MEMORY_RECALL_REVISION = 3


class _CollectorSink:
    """Thread-safe in-memory ``BrainObservationSink`` for assertions."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._events: List[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        with self._lock:
            return tuple(self._events)


class _ObservingContextSource:
    """Minimal ``BrainContextSource`` with one skipped baseline recall."""

    def conversation(self, frame, captured_at):
        return ConversationContext(
            revision=frame.revision,
            captured_at=captured_at,
            conversation_id=None,
            messages=(),
        )

    def memory_turn(self, frame, emotion, captured_at):
        del emotion

        class _SkippedSession:
            pinned_revision = MEMORY_RECALL_REVISION
            baseline_result = MemoryRecallResult(
                status="skipped",
                query="",
                pinned_revision=MEMORY_RECALL_REVISION,
                bundle=RecallBundle(recall_revision=MEMORY_RECALL_REVISION),
                reason="test_no_baseline",
            )

            def recall(self, query):
                return MemoryRecallResult(
                    status="skipped",
                    query=query,
                    pinned_revision=MEMORY_RECALL_REVISION,
                    bundle=RecallBundle(recall_revision=MEMORY_RECALL_REVISION),
                    reason="test_no_baseline",
                )

        return ReasoningMemoryTurn(
            context=MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                recall_revision=MEMORY_RECALL_REVISION,
            ),
            session=_SkippedSession(),
        )

    def capabilities(self, captured_at):
        return EffectiveCapabilities(
            revision=2,
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


class _TalkingContextSource(_ObservingContextSource):
    """Same minimal source with one prior-turn conversation row."""

    def conversation(self, frame, captured_at):
        del frame, captured_at
        return ConversationContext(
            revision=1,
            captured_at=NOW,
            conversation_id="owner:1",
            messages=(
                ConversationMessage(
                    event_id=EventId("prior-event-1"),
                    sender=ActorRef(
                        actor_id="owner-1",
                        source_kind="owner",
                        display_name="主人",
                    ),
                    occurred_at=NOW,
                    content="我们昨天聊到了蓝色小屋。",
                ),
            ),
        )


def _owner_frame() -> TurnFrame:
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    return TurnFrame(
        frame_id=EventId("frame-obs-1"),
        elfie_id=ELFIE_ID,
        revision=1,
        captured_at=NOW,
        cutoff_seq=1,
        trigger_reason=TriggerReason.CONVERSATION_QUIET,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="godot-owner", conversation_id="owner:1"
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="godot-owner",
            conversation_id="owner:1",
        ),
        events=(
            PerceptionEvent(
                meta=MessageMeta(
                    event_id=EventId("owner-event-obs-1"),
                    elfie_id=ELFIE_ID,
                    source=owner,
                    occurred_at=NOW,
                    received_at=NOW,
                    trace_id=TraceId("trace-obs-1"),
                ),
                payload=SocialPayload(
                    type="social",
                    channel_id="godot-owner",
                    conversation_id="owner:1",
                    sender=owner,
                    content="我们上一次聊到哪里了？",
                ),
            ),
        ),
    )


def _controller(
    sink: _CollectorSink,
    source: _ObservingContextSource | None = None,
) -> ReasoningRunController:
    initial = NOW.timestamp()
    energy = EnergySystem(
        {"limits": {"energy": {"initial_value": 100.0}}},
        clock=lambda: initial,
    )
    return ReasoningRunController(
        elfie_id=ELFIE_ID,
        homeostasis=energy,
        context_source=source or _ObservingContextSource(),
        hard_timeout_seconds=12.0,
        constitution=ReasoningConstitution.from_mapping(load_reasoning_constitution()),
        observation_sink=sink,
    )


def _compiled_context_events(
    sink: _CollectorSink,
) -> List[BrainObservation]:
    return [event for event in sink.snapshot() if event.kind == "compiled_context"]


def test_one_turn_emits_a_typed_compiled_context_observation() -> None:
    sink = _CollectorSink()
    controller = _controller(sink)

    task = controller.build_task(
        _owner_frame(),
        TurnId("turn-obs-1"),
        NOW.timestamp(),
        emotion=EmotionSnapshot.inactive(captured_at=NOW, revision=1),
        appraisal_scopes=(),
    )

    compiled_events = _compiled_context_events(sink)
    assert len(compiled_events) == 1
    event = compiled_events[0]
    assert event.boundary == "reasoning.context_engine"
    assert event.status == ObservationStatus.completed
    assert event.turn_id == "turn-obs-1"
    assert event.frame_id == "frame-obs-1"
    assert event.cause_event_ids == ("owner-event-obs-1",)
    assert event.duration_ms is not None
    assert event.duration_ms >= 0.0

    payload = event.payload
    assert isinstance(payload, CompiledContextObservation)
    assert payload.turn_id == "turn-obs-1"
    assert payload.frame_id == "frame-obs-1"
    assert payload.context_revision == task.request.context_revision
    assert payload.capability_revision == task.request.capability_revision == 2
    assert payload.memory_recall_revision == MEMORY_RECALL_REVISION
    assert payload.max_tokens == 1024
    assert payload.reasoning_mode == task.request.reasoning_mode
    assert payload.response_mode == task.request.response_mode.value
    assert payload.system_prompt == task.request.system_prompt
    assert payload.user_prompt == task.request.user_prompt
    assert payload.event_count == 1
    assert payload.state_update_count == 0
    assert payload.media_sample_count == 0
    assert payload.conversation_count == 0
    assert payload.conversation == ()
    assert payload.summary_count == 0
    assert payload.run_observation_count == 0
    assert payload.memory_chars == 0
    assert payload.memory_estimated_tokens == 0
    assert payload.truncated is False


def test_compiled_context_payload_carries_the_real_conversation_rows() -> None:
    sink = _CollectorSink()
    controller = _controller(sink, source=_TalkingContextSource())

    controller.build_task(
        _owner_frame(),
        TurnId("turn-obs-3"),
        NOW.timestamp(),
        emotion=EmotionSnapshot.inactive(captured_at=NOW, revision=1),
        appraisal_scopes=(),
    )

    compiled_events = _compiled_context_events(sink)
    assert len(compiled_events) == 1
    payload = compiled_events[0].payload
    assert isinstance(payload, CompiledContextObservation)
    assert payload.conversation_count == len(payload.conversation) == 1
    row = payload.conversation[0]
    assert row.event_id == "prior-event-1"
    assert row.actor_id == "owner-1"
    assert row.display_name == "主人"
    assert row.occurred_at == NOW
    assert row.content == "我们昨天聊到了蓝色小屋。"


def test_rebuild_with_a_run_observation_recompiles_and_records_it() -> None:
    sink = _CollectorSink()
    controller = _controller(sink)

    task = controller.build_task(
        _owner_frame(),
        TurnId("turn-obs-2"),
        NOW.timestamp(),
        emotion=EmotionSnapshot.inactive(captured_at=NOW, revision=1),
        appraisal_scopes=(),
    )
    rebuilt = task.context_request_builder(
        (
            CurrentRunObservation(
                kind="memory_recall",
                status="recalled",
                content="主人上次的偏好是蓝色。",
                source_ids=("assertion:claim-blue",),
                revision=MEMORY_RECALL_REVISION,
            ),
        )
    )

    assert rebuilt is not None
    compiled_events = _compiled_context_events(sink)
    assert len(compiled_events) == 2
    first = compiled_events[0].payload
    second = compiled_events[1].payload
    assert isinstance(first, CompiledContextObservation)
    assert isinstance(second, CompiledContextObservation)
    assert second.run_observation_count == 1
    assert second.event_count == first.event_count
    assert second.context_revision == first.context_revision
    assert second.memory_recall_revision == first.memory_recall_revision
    assert compiled_events[1].status == ObservationStatus.completed
    assert compiled_events[1].duration_ms is not None
    assert compiled_events[1].duration_ms >= 0.0
