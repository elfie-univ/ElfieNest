"""Coordinator energy-boundary observations on the real budget path."""

from __future__ import annotations

from threading import Lock

from elfie.brain.observation import BrainObservation
from elfie.brain.reasoning.coordinator_observations import (
    CognitiveBudgetReleasedObservation,
    CognitiveBudgetSettledObservation,
)
from elfie.brain.workspace.system import EventWorkspace
from test.elfie.brain.reasoning.test_coordinator import (
    ELFIE_ID,
    NOW,
    BlockingPlanRuntime,
    EmptyContextSource,
    RecordingPlanSink,
    _coordinator,
    _physical,
)

NOW_TS = NOW.timestamp()


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


class RaisingMemorySource(EmptyContextSource):
    def memory_turn(self, frame, emotion, captured_at):
        raise RuntimeError("memory boundary unavailable")


def test_worker_completion_settles_the_cognitive_budget_with_state() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    plan_sink = RecordingPlanSink()
    observations = CollectorSink()
    coordinator, _emotion, energy = _coordinator(
        workspace, runtime, plan_sink, observation_sink=observations
    )
    coordinator.start()
    workspace.publish(_physical(1, 0, salience=0.95))
    coordinator.notify_perception()
    assert runtime.started.wait(1), coordinator.outcomes()

    try:
        runtime.release.set()
        assert plan_sink.accepted.wait(1), coordinator.outcomes()
        settled = observations.of("energy", "budget_settled")
        assert len(settled) == 1
        event = settled[0]
        assert event.turn_id.startswith("turn_")
        assert event.frame_id
        payload = event.payload
        assert isinstance(payload, CognitiveBudgetSettledObservation)
        assert payload.stage == "worker_done"
        assert payload.consumed >= 0.25
        assert 0.0 <= payload.charged <= payload.consumed
        budget = payload.budget
        assert budget.cognitive_mode in {"normal", "long", "degraded", "emergency"}
        assert isinstance(budget.long_reasoning_allowed, bool)
        assert budget.available_cognitive_budget >= 0.0
        assert budget.reserved_cognitive_budget >= 0.0
        assert energy.reserved_cognitive_budget() == budget.reserved_cognitive_budget
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_admission_failure_releases_the_reservation() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    plan_sink = RecordingPlanSink()
    observations = CollectorSink()
    coordinator, _emotion, energy = _coordinator(
        workspace,
        runtime,
        plan_sink,
        context_source=RaisingMemorySource(),
        observation_sink=observations,
    )
    coordinator.start()
    try:
        workspace.publish(_physical(1, 0, salience=0.95))
        coordinator.notify_perception()
        coordinator.wait_for_outcome()
        coordinator.synchronize()

        released = observations.of("energy", "budget_released")
        assert len(released) == 1
        event = released[0]
        payload = event.payload
        assert isinstance(payload, CognitiveBudgetReleasedObservation)
        assert payload.stage == "admission_failed"
        assert payload.released is True
        assert payload.budget.energy == energy.energy
        assert energy.reserved_cognitive_budget() == 0.0
        assert coordinator.outcomes()[0].status.value == "failed"
    finally:
        coordinator.stop()
        coordinator.join()
