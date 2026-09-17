"""Coordinator emotion-boundary observations on the real affect path."""

from __future__ import annotations

from threading import Lock

from elfie.brain.emotion.appraiser import BrainClockPulse
from elfie.brain.observation import BrainObservation
from elfie.brain.reasoning.coordinator_observations import (
    EmotionAppraisalInputObservation,
    EmotionCandidateObservation,
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


def _observation_coordinator(
    workspace: EventWorkspace,
    runtime: BlockingPlanRuntime,
    plan_sink: RecordingPlanSink,
    observation_sink: CollectorSink,
):
    return _coordinator(
        workspace, runtime, plan_sink, observation_sink=observation_sink
    )


def test_fast_path_emits_appraisal_input_and_candidate_with_dimensions() -> None:
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    plan_sink = RecordingPlanSink()
    observations = CollectorSink()
    coordinator, emotion, _energy = _observation_coordinator(
        workspace, runtime, plan_sink, observations
    )
    coordinator.start()
    workspace.publish(
        _social(1, 0, source_kind="owner", text="I hate you"),
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW_TS + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        appraisals = observations.of("emotion", "appraisal_input")
        assert len(appraisals) == 1
        appraisal = appraisals[0]
        assert appraisal.turn_id.startswith("turn_")
        assert appraisal.frame_id
        assert appraisal.cause_event_ids == ("social-1",)
        payload = appraisal.payload
        assert isinstance(payload, EmotionAppraisalInputObservation)
        assert payload.event_id == "social-1"
        assert payload.source == "social"
        assert payload.appraisals
        assert any(
            effect.channel == "anger" and effect.direction == "increase"
            for item in payload.appraisals
            for effect in item.effects
        )
        assert payload.guidance_applied is False

        candidates = observations.of("emotion", "emotion_candidate")
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.frame_id == appraisal.frame_id
        fast = candidate.payload
        assert isinstance(fast, EmotionCandidateObservation)
        assert fast.stage == "fast"
        assert len(fast.dimensions) == 6
        anger = next(item for item in fast.dimensions if item.name == "anger")
        assert anger.after > anger.before
        assert "anger" in fast.changed_dimensions
        assert anger.after == emotion.get_emotion_value("anger")
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()


def test_model_feedback_emits_the_reviewed_slow_candidate() -> None:
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
    plan_sink = RecordingPlanSink()
    observations = CollectorSink()
    coordinator, emotion, _energy = _observation_coordinator(
        workspace, runtime, plan_sink, observations
    )
    coordinator.start()
    workspace.publish(
        _social(1, 0, source_kind="owner", text="I hate you"),
    )
    coordinator.notify_perception()
    coordinator.post_clock(BrainClockPulse(timestamp=NOW_TS + 0.5))
    assert runtime.started.wait(1), coordinator.outcomes()
    coordinator.synchronize()

    try:
        runtime.release.set()
        assert plan_sink.accepted.wait(1), coordinator.outcomes()
        slow_events = [
            event
            for event in observations.of("emotion", "emotion_candidate")
            if event.payload.stage == "slow"
        ]
        assert len(slow_events) == 1
        assert slow_events[0].status.value == "completed"
        slow = slow_events[0].payload
        assert isinstance(slow, EmotionCandidateObservation)
        happiness = next(item for item in slow.dimensions if item.name == "happiness")
        assert happiness.after > happiness.before
        assert (
            emotion.get_emotion_value("happiness")
            > emotion.parameters("happiness").baseline
        )
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()
