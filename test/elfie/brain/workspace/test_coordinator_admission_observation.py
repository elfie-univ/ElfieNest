"""Workspace admission observations from the real coordinator claim path."""

from __future__ import annotations

from threading import Lock

from elfie.brain.emotion.appraiser import BrainClockPulse
from elfie.brain.observation import BrainObservation
from elfie.brain.reasoning.coordinator_observations import (
    WorkspaceFrameAdmissionObservation,
)
from elfie.brain.workspace.system import EventWorkspace
from test.elfie.brain.reasoning.test_coordinator import (
    ELFIE_ID,
    NOW,
    BlockingPlanRuntime,
    RecordingPlanSink,
    _coordinator,
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


def test_quiet_conversation_claims_one_admitted_communication_frame() -> None:
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
        coordinator.synchronize()

        claims = observations.of("workspace", "frame_claim")
        assert len(claims) == 1
        event = claims[0]
        assert event.status.value == "completed"
        assert event.turn_id.startswith("turn_")
        assert event.frame_id
        payload = event.payload
        assert isinstance(payload, WorkspaceFrameAdmissionObservation)
        assert payload.admitted is True
        assert payload.detail is None
        assert payload.source_domain == "communication"
        assert payload.trigger_reason == "conversation_quiet"
        assert payload.cutoff_seq >= 1
        assert payload.event_count == 1
        assert payload.max_event_salience == 0.5
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_empty_claim_emits_the_no_perception_skip() -> None:
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
    runtime = BlockingPlanRuntime()
    plan_sink = RecordingPlanSink()
    observations = CollectorSink()
    coordinator, _emotion, _energy = _coordinator(
        workspace, runtime, plan_sink, observation_sink=observations
    )
    coordinator.start()
    try:
        coordinator.notify_perception()
        coordinator.synchronize()

        claims = observations.of("workspace", "frame_claim")
        assert len(claims) == 1
        event = claims[0]
        assert event.status.value == "skipped"
        assert event.frame_id == ""
        payload = event.payload
        assert isinstance(payload, WorkspaceFrameAdmissionObservation)
        assert payload.admitted is False
        assert payload.detail == "no_perception"
        assert payload.trigger_reason == "emergency"
        assert payload.cutoff_seq == 1
        assert payload.event_count == 0
    finally:
        coordinator.stop()
        coordinator.join()
