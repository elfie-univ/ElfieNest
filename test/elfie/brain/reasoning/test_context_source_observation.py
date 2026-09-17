"""Orientation-boundary observations from the real context provider."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from elfie.brain.activity.context import ActivityContextReader
from elfie.brain.activity.system import InMemoryActivityStore
from elfie.brain.consolidation.system import CognitiveConsolidationSystem
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.motivation.system import MotivationSystem
from elfie.brain.observation import BrainObservation
from elfie.brain.orientation.system import OrientationSystem
from elfie.brain.reasoning.context_source import BrainContextProvider
from elfie.brain.reasoning.context_types import (
    BodyCapabilityDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.conversation_context import ReasoningContextWorkspace
from elfie.brain.reasoning.coordinator_observations import (
    OrientationSnapshotObservation,
)
from elfie.brain.reasoning.memory_context import ReasoningMemoryBridge
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.brain.state_lifecycle import StateCandidate
from elfie.brain.workspace.contracts import (
    EmbodiedScope,
    ExternalExecutionDomain,
    PerceptionEvent,
    PerceptionStateUpdate,
    PhysicalModality,
    PhysicalPayload,
    ResponseScope,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
    TurnId,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-orientation-obs")


class CollectorSink:
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: list[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> tuple[BrainObservation, ...]:
        with self._lock:
            return tuple(self._events)

    def of(self, boundary: str, kind: str) -> tuple[BrainObservation, ...]:
        return tuple(
            event
            for event in self.snapshot()
            if event.boundary == boundary and event.kind == kind
        )


def _provider(observation_sink: CollectorSink) -> BrainContextProvider:
    memory = MemorySystem(
        SQLiteMemoryStoreAdapter.in_memory(),
        elfie_id="elfie-orientation-obs",
        initial_at=NOW,
    )
    return BrainContextProvider(
        memory=ReasoningMemoryBridge(memory),
        conversations=ReasoningContextWorkspace(),
        activities=ActivityContextReader(InMemoryActivityStore(), capacity=16),
        capability_reader=lambda captured_at, _authorized: EffectiveCapabilities(
            revision=1,
            captured_at=captured_at,
            current_body=BodyCapabilityDescriptor(
                body_id="body-1",
                body_generation=3,
                capability_revision=1,
                sensors=("vision",),
                actions=("walk",),
            ),
            connected_channels=(),
        ),
        clock=lambda: NOW,
        orientation=OrientationSystem(initial_at=NOW),
        selfhood=SelfhoodSystem(initial_at=NOW),
        motivation=MotivationSystem(initial_at=NOW),
        consolidation=CognitiveConsolidationSystem(
            pending_episode_ids=memory.pending_consolidation_ids,
            consolidate=lambda limit: memory.run_consolidation(max_episodes=limit),
            initial_at=NOW,
        ),
        observation_sink=observation_sink,
    )


def _capabilities(captured_at: datetime) -> EffectiveCapabilities:
    return EffectiveCapabilities(
        revision=1,
        captured_at=captured_at,
        current_body=BodyCapabilityDescriptor(
            body_id="body-1",
            body_generation=3,
            capability_revision=1,
            sensors=("vision",),
            actions=("walk",),
        ),
        connected_channels=(),
    )


def _embodied_frame() -> TurnFrame:
    actor = ActorRef(actor_id=ActorId("neighbor"), source_kind="room")
    meta = MessageMeta(
        event_id=EventId("room-call"),
        elfie_id=ELFIE_ID,
        source=actor,
        occurred_at=NOW,
        received_at=NOW,
        trace_id=TraceId("orientation-obs-trace"),
    )
    return TurnFrame(
        frame_id=EventId("frame-embodied"),
        elfie_id=ELFIE_ID,
        revision=1,
        captured_at=NOW,
        cutoff_seq=2,
        trigger_reason=TriggerReason.SALIENCE,
        source_domain=SourceDomain.EMBODIED,
        interaction_scope=EmbodiedScope(body_id="body-1", body_generation=3),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.NERVOUS_SYSTEM,
            body_id="body-1",
            body_generation=3,
        ),
        events=(
            PerceptionEvent(
                meta=meta,
                payload=PhysicalPayload(
                    type="physical",
                    body_id="body-1",
                    body_generation=3,
                    modality=PhysicalModality.UTTERANCE,
                    content="come here",
                ),
            ),
        ),
        state_updates=(
            PerceptionStateUpdate(
                meta=MessageMeta(
                    event_id=EventId("location-1"),
                    elfie_id=ELFIE_ID,
                    source=actor,
                    occurred_at=NOW,
                    received_at=NOW,
                    trace_id=TraceId("orientation-obs-trace"),
                ),
                body_id="body-1",
                body_generation=3,
                state_key="body:body-1:orientation:location",
                revision=1,
                value="dorm-01",
            ),
        ),
    )


def test_orientation_candidate_emits_the_proposed_snapshot() -> None:
    sink = CollectorSink()
    provider = _provider(sink)
    frame = _embodied_frame()

    candidate = provider.orientation_candidate(
        frame,
        NOW,
        TurnId("turn-orientation-obs"),
        _capabilities(NOW),
    )

    assert isinstance(candidate, StateCandidate)
    events = sink.of("orientation", "orientation_snapshot")
    assert len(events) == 1
    event = events[0]
    assert event.status.value == "completed"
    assert event.turn_id == "turn-orientation-obs"
    assert event.frame_id == "frame-embodied"
    payload = event.payload
    assert isinstance(payload, OrientationSnapshotObservation)
    assert payload.revision == candidate.value.revision
    assert payload.body_id == "body-1"
    assert payload.body_generation == 3
    assert payload.location == "dorm-01"
    assert payload.location_source == "observation"
    assert payload.freshness == "current"
    assert payload.activity_id is None
    assert payload.affordance_count >= 0
