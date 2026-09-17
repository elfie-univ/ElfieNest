"""Run Controller / Context Engine / Selfhood / Workspace emit their events."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import List, Tuple

import pytest

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.memory.contracts import MemoryContext
from elfie.brain.memory.memory_records import RecallBundle
from elfie.brain.observation import BrainObservation, ObservationStatus
from elfie.brain.reasoning.agent_loop_observations import (
    AgentLoopActionObservation,
    AgentLoopGuardObservation,
    AgentLoopGuardStopObservation,
    AgentLoopJudgeObservation,
    AgentLoopObservationRecorded,
    AgentLoopRunFailedObservation,
)
from elfie.brain.reasoning.context_types import (
    ConversationContext,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.conversation_context import ReasoningContextWorkspace
from elfie.brain.reasoning.coordinator_turn import ReasoningRunController
from elfie.brain.reasoning.memory_context import (
    MemoryRecallResult,
    ReasoningMemoryTurn,
)
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.reasoning.observation_payloads import CompiledContextObservation
from elfie.brain.reasoning.run_controller_observations import (
    CognitiveBudgetReservedObservation,
    ContextTrimObservation,
    ConversationAppendedObservation,
    ReasoningBudgetFrozenObservation,
    ReasoningContextFrozenObservation,
    ReasoningModeSelectedObservation,
    SelfhoodProjectionObservation,
)
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
ELFIE_ID = ElfieId("elfie-run-ctrl")
SELFHOOD = SelfhoodPromptProjection(
    revision=4,
    captured_at=NOW,
    identity_core_text="我是小狐，是 ElfieNest 的居民。",
    adaptive_self_text="我会先观察，再清楚地表达。",
)


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

    def of(self, boundary: str, kind: str) -> Tuple[BrainObservation, ...]:
        return tuple(
            event
            for event in self.snapshot()
            if (event.boundary, event.kind) == (boundary, kind)
        )


class _StaticContextSource:
    """Minimal ``BrainContextSource`` returning one skipped baseline recall."""

    def __init__(self, selfhood: SelfhoodPromptProjection = SELFHOOD) -> None:
        self._selfhood = selfhood

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
            pinned_revision = 3
            baseline_result = MemoryRecallResult(
                status="skipped",
                query="",
                pinned_revision=3,
                bundle=RecallBundle(recall_revision=3),
                reason="test_no_baseline",
            )

            def recall(self, query):
                return MemoryRecallResult(
                    status="skipped",
                    query=query,
                    pinned_revision=3,
                    bundle=RecallBundle(recall_revision=3),
                    reason="test_no_baseline",
                )

        return ReasoningMemoryTurn(
            context=MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                recall_revision=3,
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
        return self._selfhood


class _WorkspaceContextSource(_StaticContextSource):
    """Source whose conversation rows come from a real workspace."""

    def __init__(self) -> None:
        super().__init__()
        self._workspace = ReasoningContextWorkspace(history_capacity=3)

    def conversation(self, frame, captured_at):
        return self._workspace.observe(frame, captured_at)


def _frame(
    *,
    frame_id: str,
    content: str,
    salience: float = 0.5,
) -> TurnFrame:
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    return TurnFrame(
        frame_id=EventId(frame_id),
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
                    event_id=EventId(f"{frame_id}-event"),
                    elfie_id=ELFIE_ID,
                    source=owner,
                    occurred_at=NOW,
                    received_at=NOW,
                    trace_id=TraceId(f"trace-{frame_id}"),
                ),
                payload=SocialPayload(
                    type="social",
                    channel_id="godot-owner",
                    conversation_id="owner:1",
                    sender=owner,
                    content=content,
                ),
                salience=salience,
            ),
        ),
    )


def _controller(
    sink: _CollectorSink | None,
    source: _StaticContextSource | None = None,
    *,
    initial_energy: float = 100.0,
) -> ReasoningRunController:
    initial = NOW.timestamp()
    energy = EnergySystem(
        {"limits": {"energy": {"initial_value": initial_energy}}},
        clock=lambda: initial,
    )
    return ReasoningRunController(
        elfie_id=ELFIE_ID,
        homeostasis=energy,
        context_source=source or _StaticContextSource(),
        hard_timeout_seconds=12.0,
        constitution=ReasoningConstitution.from_mapping(load_reasoning_constitution()),
        observation_sink=sink,
    )


def _build(controller: ReasoningRunController, frame: TurnFrame):
    return controller.build_task(
        frame,
        TurnId("turn-run-ctrl"),
        NOW.timestamp(),
        emotion=EmotionSnapshot.inactive(captured_at=NOW, revision=1),
        appraisal_scopes=(),
    )


def test_direct_turn_emits_reserve_mode_budget_and_trim_events() -> None:
    sink = _CollectorSink()
    controller = _controller(sink)

    _build(controller, _frame(frame_id="frame-direct", content="你好呀"))

    reserves = sink.of("energy", "budget_reserve")
    assert len(reserves) == 1
    reserve = reserves[0]
    assert reserve.turn_id == "turn-run-ctrl"
    assert reserve.frame_id == "frame-direct"
    assert reserve.cause_event_ids == ("frame-direct-event",)
    assert reserve.status is ObservationStatus.completed
    payload = reserve.payload
    assert isinstance(payload, CognitiveBudgetReservedObservation)
    assert payload.mode == "long"
    assert payload.source == "normal"
    assert payload.granted > 0.0
    assert payload.responsive is True
    assert payload.budget.reserved_cognitive_budget >= payload.granted

    projections = sink.of("selfhood", "projection_snapshot")
    assert len(projections) == 1
    projection = projections[0]
    assert projection.frame_id == "frame-direct"
    projection_payload = projection.payload
    assert isinstance(projection_payload, SelfhoodProjectionObservation)
    assert projection_payload.revision == SELFHOOD.revision
    assert projection_payload.identity_core_text == SELFHOOD.identity_core_text
    assert projection_payload.adaptive_self_text == SELFHOOD.adaptive_self_text
    assert projection_payload.projected_at == SELFHOOD.captured_at

    modes = sink.of("reasoning.run_controller", "mode_selected")
    assert len(modes) == 1
    mode = modes[0]
    assert mode.status is ObservationStatus.completed
    mode_payload = mode.payload
    assert isinstance(mode_payload, ReasoningModeSelectedObservation)
    assert mode_payload.depth == "direct"
    assert mode_payload.depth_basis == "default_direct"
    assert mode_payload.reasoning_mode == "fast"
    assert mode_payload.response_mode == "direct_reply"
    assert mode_payload.requires_model is True
    assert mode_payload.structured_owner_reply is True
    assert mode_payload.fast_owner_reply is True
    assert mode_payload.effective_tools == ()
    assert mode_payload.skill_count == 0

    budgets = sink.of("reasoning.run_controller", "budget_frozen")
    assert len(budgets) == 1
    budget_payload = budgets[0].payload
    assert isinstance(budget_payload, ReasoningBudgetFrozenObservation)
    assert budget_payload.max_steps == 3
    assert budget_payload.max_model_calls == 1
    assert budget_payload.max_planned_model_calls is None
    assert budget_payload.max_tool_calls == 0
    assert budget_payload.deadline_seconds == 12.0
    assert budget_payload.hard_deadline_seconds == 12.0
    assert budget_payload.max_context_tokens == 1024
    assert budget_payload.cognitive_mode == "long"
    assert budget_payload.long_reasoning_allowed is True

    trims = sink.of("reasoning.context_engine", "context_trimmed")
    assert len(trims) == 1
    trim = trims[0]
    assert trim.frame_id == "frame-direct"
    trim_payload = trim.payload
    assert isinstance(trim_payload, ContextTrimObservation)
    assert trim_payload.max_tokens == 1024
    assert trim_payload.memory_budget == 0
    assert trim_payload.event_budget == 256
    assert trim_payload.truncated is False
    assert trim_payload.memory_truncated is False
    assert trim_payload.event_truncated_count == 0
    assert trim_payload.history_truncated_count == 0

    assert len(sink.of("reasoning.context_engine", "compiled_context")) == 1
    reserve_event = sink.of("energy", "budget_reserve")[0]
    assert reserve_event.duration_ms is not None
    assert (
        sink.of("reasoning.run_controller", "mode_selected")[0].duration_ms is not None
    )
    assert (
        sink.of("reasoning.run_controller", "budget_frozen")[0].duration_ms is not None
    )
    assert (
        sink.of("reasoning.context_engine", "context_trimmed")[0].duration_ms
        is not None
    )
    assert (
        sink.of("reasoning.context_engine", "compiled_context")[0].duration_ms
        is not None
    )
    assert sink.of("selfhood", "projection_snapshot")[0].duration_ms is not None
    sequences = [event.sequence for event in sink.snapshot()]
    assert sequences == sorted(sequences)


def test_context_frozen_event_captures_the_immutable_reasoning_input() -> None:
    sink = _CollectorSink()
    controller = _controller(sink)

    _build(controller, _frame(frame_id="frame-frozen", content="冻结检查"))

    events = sink.of("reasoning.run_controller", "context_frozen")
    assert len(events) == 1
    event = events[0]
    payload = event.payload
    assert isinstance(payload, ReasoningContextFrozenObservation)
    assert event.frame_id == "frame-frozen"
    assert event.status is ObservationStatus.completed
    assert event.duration_ms is None
    assert payload.context_revision == 1
    assert payload.constitution_version >= 1
    assert payload.emotion.revision == 1
    assert payload.homeostasis.reserved_cognitive_budget > 0.0
    assert payload.orientation.freshness == "unknown"
    assert payload.selfhood == SELFHOOD
    assert (
        event.sequence
        < sink.of("reasoning.run_controller", "mode_selected")[0].sequence
    )


def test_deliberate_turn_emits_the_deliberate_mode_decision() -> None:
    sink = _CollectorSink()
    controller = _controller(sink)

    _build(
        controller,
        _frame(frame_id="frame-deep", content="紧急情况", salience=0.95),
    )

    modes = sink.of("reasoning.run_controller", "mode_selected")
    assert len(modes) == 1
    mode_payload = modes[0].payload
    assert isinstance(mode_payload, ReasoningModeSelectedObservation)
    assert mode_payload.depth == "deliberate"
    assert mode_payload.depth_basis == "communication_salience_or_priority"
    assert mode_payload.reasoning_mode == "long"

    budget_payload = sink.of("reasoning.run_controller", "budget_frozen")[0].payload
    assert isinstance(budget_payload, ReasoningBudgetFrozenObservation)
    assert budget_payload.max_steps is None
    assert budget_payload.max_model_calls == 3
    assert budget_payload.max_planned_model_calls == 8
    assert budget_payload.deadline_seconds is None


def test_emergency_budget_trims_oversized_event_content() -> None:
    sink = _CollectorSink()
    controller = _controller(sink, initial_energy=5.0)

    _build(
        controller,
        _frame(frame_id="frame-trim", content=" ".join(["词"] * 400)),
    )

    trims = sink.of("reasoning.context_engine", "context_trimmed")
    assert len(trims) == 1
    trim_payload = trims[0].payload
    assert isinstance(trim_payload, ContextTrimObservation)
    assert trim_payload.max_tokens == 256
    assert trim_payload.content_budget == 226
    assert trim_payload.event_budget == 150
    assert trim_payload.truncated is True
    assert trim_payload.event_truncated_count == 1

    compiled = sink.of("reasoning.context_engine", "compiled_context")[0]
    assert isinstance(compiled.payload, CompiledContextObservation)
    assert compiled.payload.truncated is True


def test_observe_conversation_records_partition_key_and_summary_coverage() -> None:
    sink = _CollectorSink()
    source = _WorkspaceContextSource()
    controller = _controller(sink, source)

    for index in range(4):
        controller.observe_conversation(
            _frame(frame_id=f"frame-conv-{index}", content=f"第 {index} 句"),
            NOW,
            turn_id=TurnId("turn-conv"),
            cause_event_ids=(EventId(f"frame-conv-{index}-event"),),
        )

    appends = sink.of("reasoning.context_workspace", "conversation_appended")
    assert len(appends) == 4
    assert appends[0].turn_id == "turn-conv"
    assert appends[0].cause_event_ids == ("frame-conv-0-event",)
    assert appends[0].duration_ms is not None
    first = appends[0].payload
    assert isinstance(first, ConversationAppendedObservation)
    assert first.channel_id == "godot-owner"
    assert first.conversation_id == "owner:1"
    assert first.input_event_ids == ("frame-conv-0-event",)
    assert first.message_count == 1
    assert first.summaries == ()

    last = appends[3].payload
    assert isinstance(last, ConversationAppendedObservation)
    assert last.message_count == 2
    assert len(last.summaries) == 1
    summary = last.summaries[0]
    assert summary.version == 1
    assert summary.source_event_ids == (
        "frame-conv-0-event",
        "frame-conv-1-event",
    )
    assert appends[3].frame_id == "frame-conv-3"


def test_controller_emits_nothing_and_constructs_nothing_without_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError("observation constructed while no sink is wired")

    monkeypatch.setattr(BrainObservation, "__init__", _forbid_construction)
    for payload_type in (
        CognitiveBudgetReservedObservation,
        ContextTrimObservation,
        ConversationAppendedObservation,
        ReasoningBudgetFrozenObservation,
        ReasoningModeSelectedObservation,
        SelfhoodProjectionObservation,
        ReasoningContextFrozenObservation,
        CompiledContextObservation,
    ):
        monkeypatch.setattr(payload_type, "__init__", _forbid_construction)

    controller = _controller(None)
    _build(controller, _frame(frame_id="frame-zero", content="你好"))
    controller.observe_conversation(
        _frame(frame_id="frame-zero-conv", content="你好"), NOW
    )


def test_agent_loop_decision_payloads_are_the_declared_frozen_models() -> None:
    """Guard the payload module against accidental envelope field drift."""
    declared = (
        AgentLoopActionObservation,
        AgentLoopGuardObservation,
        AgentLoopGuardStopObservation,
        AgentLoopJudgeObservation,
        AgentLoopObservationRecorded,
        AgentLoopRunFailedObservation,
    )
    for payload_type in declared:
        assert payload_type.model_config.get("frozen") is True
