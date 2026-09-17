"""Elfie Lab wiring of the unified ``BrainObservationSink`` surface."""

import threading

from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie.brain.observation import BrainObservation


class _CollectorSink:
    """Minimal thread-safe sink used to observe the lab's Brain wiring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> tuple[BrainObservation, ...]:
        with self._lock:
            return tuple(self._events)


def test_lab_session_forwards_single_observation_sink(tmp_path):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("观测精灵")
    sink = _CollectorSink()
    session = ElfieLabSession(spec, storage, observation_sink=sink)
    try:
        turn = session.run_turn(StimulusBundle(message="你还记得我的偏好吗？"), "mock")
    finally:
        session.close()

    events = sink.snapshot()
    kinds = {event.kind for event in events}
    assert turn["result"]["success"] is True
    assert len(events) >= 1
    assert kinds <= {
        "turn_opened",
        "recall_started",
        "recall_result",
        "compiled_context",
        "context_frozen",
        "context_trimmed",
        "model_call",
        "orientation_snapshot",
        "frame_claim",
        "emotion_candidate",
        "drive_evaluated",
        "decision_routed",
        "mode_selected",
        "action_decoded",
        "guard",
        "judge",
        "projection_snapshot",
        "conversation_appended",
        "budget_frozen",
        "budget_reserve",
        "budget_settled",
        "candidate_scored",
        "selection_summary",
        "run_failed",
    }
    assert "compiled_context" in kinds
    assert all(isinstance(event, BrainObservation) for event in events)
    compiled = [event for event in events if event.kind == "compiled_context"]
    assert all(event.turn_id for event in compiled)


def test_lab_session_runs_production_default_without_observation_sink(tmp_path):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("默认观测精灵")
    session = ElfieLabSession(spec, storage, observation_sink=None)
    try:
        turn = session.run_turn(StimulusBundle(message="今天心情怎么样？"), "mock")
    finally:
        session.close()

    assert turn["result"]["success"] is True
    assert turn["trace"]["stages"]["cognitive_turn"]["status"] == "completed"
