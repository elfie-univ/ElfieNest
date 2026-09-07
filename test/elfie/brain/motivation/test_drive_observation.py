"""Drive-boundary observations from the real context provider."""

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
from elfie.brain.reasoning.context_types import EffectiveCapabilities
from elfie.brain.reasoning.conversation_context import ReasoningContextWorkspace
from elfie.brain.reasoning.coordinator_observations import (
    MotivationDriveEvaluatedObservation,
)
from elfie.brain.reasoning.memory_context import ReasoningMemoryBridge
from elfie.brain.selfhood.system import SelfhoodSystem
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)


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
        elfie_id="elfie-drive-obs",
        initial_at=NOW,
    )
    return BrainContextProvider(
        memory=ReasoningMemoryBridge(memory),
        conversations=ReasoningContextWorkspace(),
        activities=ActivityContextReader(InMemoryActivityStore(), capacity=16),
        capability_reader=lambda captured_at, _authorized: EffectiveCapabilities(
            revision=0,
            captured_at=captured_at,
            current_body=None,
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


def _single_event(sink: CollectorSink) -> MotivationDriveEvaluatedObservation:
    events = sink.of("motivation", "drive_evaluated")
    assert len(events) == 1
    assert events[0].status.value == "completed"
    payload = events[0].payload
    assert isinstance(payload, MotivationDriveEvaluatedObservation)
    return payload


def _last_event(sink: CollectorSink) -> MotivationDriveEvaluatedObservation:
    events = sink.of("motivation", "drive_evaluated")
    assert events
    payload = events[-1].payload
    assert isinstance(payload, MotivationDriveEvaluatedObservation)
    return payload


def test_pressure_above_threshold_emits_a_recovery_candidate() -> None:
    sink = CollectorSink()
    provider = _provider(sink)

    candidate = provider.evaluate_motivation(
        energy=5.0,
        fatigue=10.0,
        sleeping=False,
        now=NOW,
        blocked=False,
    )

    assert candidate is not None
    payload = _single_event(sink)
    assert payload.energy == 5.0
    assert payload.fatigue == 10.0
    assert payload.sleeping is False
    assert payload.blocked is False
    assert payload.pressure > 0.0
    assert payload.status == "cooldown"
    assert payload.skip_reason is None
    assert payload.candidate_id == str(candidate.candidate_id)
    assert payload.candidate_id.startswith("motivation:recovery:")
    assert payload.goal
    assert payload.candidate_pressure == candidate.pressure
    assert payload.candidate_reason
    assert payload.cooldown_until is not None
    assert payload.last_trigger_id == str(candidate.candidate_id)


def test_blocked_drive_emits_the_block_reason_without_candidate() -> None:
    sink = CollectorSink()
    provider = _provider(sink)

    candidate = provider.evaluate_motivation(
        energy=5.0,
        fatigue=10.0,
        sleeping=False,
        now=NOW,
        blocked=True,
    )

    assert candidate is None
    payload = _single_event(sink)
    assert payload.blocked is True
    assert payload.status == "blocked"
    assert payload.skip_reason == "drive_blocked"
    assert payload.candidate_id is None
    assert payload.goal is None


def test_cooldown_window_emits_the_cooldown_skip_reason() -> None:
    sink = CollectorSink()
    provider = _provider(sink)
    provider.evaluate_motivation(
        energy=5.0, fatigue=10.0, sleeping=False, now=NOW, blocked=False
    )

    candidate = provider.evaluate_motivation(
        energy=5.0, fatigue=10.0, sleeping=False, now=NOW, blocked=False
    )

    assert candidate is None
    payload = _last_event(sink)
    assert payload.status == "cooldown"
    assert payload.skip_reason == "cooldown"
    assert payload.cooldown_until is not None


def test_no_pressure_emits_the_ready_skip_reason() -> None:
    sink = CollectorSink()
    provider = _provider(sink)

    candidate = provider.evaluate_motivation(
        energy=100.0,
        fatigue=0.0,
        sleeping=False,
        now=NOW,
        blocked=False,
    )

    assert candidate is None
    payload = _single_event(sink)
    assert payload.pressure == 0.0
    assert payload.status == "ready"
    assert payload.skip_reason == "no_pressure"


def test_sleeping_drive_emits_the_sleeping_skip_reason() -> None:
    sink = CollectorSink()
    provider = _provider(sink)

    candidate = provider.evaluate_motivation(
        energy=5.0,
        fatigue=10.0,
        sleeping=True,
        now=NOW,
        blocked=False,
    )

    assert candidate is None
    payload = _single_event(sink)
    assert payload.sleeping is True
    assert payload.status == "ready"
    assert payload.skip_reason == "sleeping"
