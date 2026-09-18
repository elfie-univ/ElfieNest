"""Session-level proof that the lab trace memory view is built from raw events.

These tests drive a real ``ElfieLabSession`` turn and assert that the
projection's memory block (status/query/evidence/selected) matches the
``BrainObservation`` envelopes captured during the turn — with no prompt
reverse-derivation anywhere.  The turn without a caller-supplied sink also
proves the session's internal capture still feeds the projection.
"""

import threading

from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie.brain.memory.memory_records import ClosedEpisode
from elfie.brain.observation import BrainObservation
from elfie.diagnostics import ElfieDiagnostics


class _CollectorSink:
    """Caller-side sink proving the session still forwards every event."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list = []

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> tuple:
        with self._lock:
            return tuple(self._events)


def test_session_turn_projects_memory_block_from_raw_events(tmp_path):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("事件投影精灵")
    collector = _CollectorSink()
    session = ElfieLabSession(spec, storage, observation_sink=collector)
    try:
        memory = ElfieDiagnostics(session.elfie).memory
        memory.record_closed_episode(
            _episode("lab-recall-episode", "主人在窗边陪我玩耍 lab-recall-token")
        )

        turn = session.run_turn(
            StimulusBundle(message="你还记得 lab-recall-token 吗？"),
            "mock",
        )
    finally:
        session.close()

    assert turn["result"]["success"] is True
    memory_view = turn["trace"]["stages"]["observability"]["memory"]
    assert memory_view["status"] == "recalled"
    assert memory_view["query"] == "你还记得 lab-recall-token 吗？"
    point_kinds = [point["kind"] for point in memory_view["returned_points"]]
    assert "episode" in point_kinds
    assert "lab-recall-episode" in [
        point["id"] for point in memory_view["returned_points"]
    ]

    # Provenance: the projection's values are copied from the raw envelopes.
    baseline_event = memory_view["raw"]["baseline"]
    assert baseline_event["kind"] == "recall_result"
    assert baseline_event["payload"]["query"] == memory_view["query"]
    assert baseline_event["payload"]["status"] == memory_view["status"]

    captured = collector.snapshot()
    assert any(event.kind == "recall_result" for event in captured)
    assert any(event.kind == "compiled_context" for event in captured)


def test_session_turn_without_recall_intent_projects_skipped_no_hit(tmp_path):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("无回忆精灵")
    session = ElfieLabSession(spec, storage)
    try:
        turn = session.run_turn(StimulusBundle(message="你好"), "mock")
    finally:
        session.close()

    assert turn["result"]["success"] is True
    memory_view = turn["trace"]["stages"]["observability"]["memory"]
    assert memory_view["status"] == "skipped"
    assert memory_view["reason"] == "baseline_recall_not_relevant"
    assert memory_view["returned_points"] == []
    assert memory_view["selected"] == []


def _episode(episode_id: str, content: str) -> ClosedEpisode:
    return ClosedEpisode(
        episode_id=episode_id,
        idempotency_key=episode_id,
        occurred_from="2026-01-01T00:00:00+00:00",
        content_text=content,
        importance=0.8,
        emotion="happy",
        emotion_intensity=0.6,
    )
