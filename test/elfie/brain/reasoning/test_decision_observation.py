"""Decision-boundary observations at the real govern_decision call sites."""

from __future__ import annotations

from threading import Lock

from elfie.brain.emotion.appraiser import BrainClockPulse
from elfie.brain.observation import BrainObservation
from elfie.brain.reasoning.coordinator_observations import DecisionRoutedObservation
from elfie.brain.workspace.system import EventWorkspace
from test.elfie.brain.reasoning.test_coordinator import (
    ELFIE_ID,
    NOW,
    BlockingPlanRuntime,
    RecordingPlanSink,
    _coordinator,
    _physical,
    _social,
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


def test_completed_turn_emits_the_governed_decision() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    plan_sink = RecordingPlanSink()
    observations = CollectorSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace, runtime, plan_sink, observation_sink=observations
    )
    coordinator.start()
    try:
        workspace.publish(
            _social(1, 0, source_kind="owner", text="hello there"),
        )
        coordinator.notify_perception()
        coordinator.post_clock(BrainClockPulse(timestamp=NOW_TS + 0.5))
        assert runtime.started.wait(1), coordinator.outcomes()
        runtime.release.set()
        assert plan_sink.accepted.wait(1), coordinator.outcomes()
        coordinator.synchronize()

        routed = observations.of("decision_boundary", "decision_routed")
        assert len(routed) == 1
        event = routed[0]
        assert event.status.value == "completed"
        assert event.turn_id.startswith("turn_")
        assert event.frame_id
        payload = event.payload
        assert isinstance(payload, DecisionRoutedObservation)
        assert payload.plan_id
        assert payload.intent_types == ("message",)
        assert payload.interaction_scope_kind == "communication"
        assert payload.source_domain == "communication"
        assert payload.response_domain == "communication"
        assert payload.response_channel_id == "chat"
        assert payload.response_conversation_id == "conversation-1"
        assert payload.memory_eligible is True
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_hard_timeout_emits_the_routed_noop_decision() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    plan_sink = RecordingPlanSink()
    observations = CollectorSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace,
        runtime,
        plan_sink,
        observation_sink=observations,
    )
    coordinator._hard_timeout = 0.05
    coordinator.start()
    try:
        workspace.publish(_physical(1, 0, salience=0.95))
        coordinator.notify_perception()
        assert runtime.started.wait(1), coordinator.outcomes()
        coordinator.post_clock(BrainClockPulse(timestamp=NOW_TS + 0.5))
        coordinator.wait_for_outcome()
        coordinator.synchronize()

        routed = observations.of("decision_boundary", "decision_routed")
        assert len(routed) == 1
        payload = routed[0].payload
        assert isinstance(payload, DecisionRoutedObservation)
        assert payload.intent_types == ("noop",)
        assert payload.source_domain == "embodied"
        assert payload.interaction_scope_kind == "embodied"
        assert payload.routed is True
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()
