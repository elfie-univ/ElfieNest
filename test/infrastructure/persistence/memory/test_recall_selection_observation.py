"""Recall-selection observations at the SQLite Memory storage boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

import pytest

from elfie.brain.memory.memory_records import ClosedEpisode, RecallRequest
from elfie.brain.memory.observation_payloads import (
    RecallCandidateScored,
    RecallSelectionSummary,
)
from elfie.brain.observation import BrainObservation
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc)


class _CollectorSink:
    """Minimal thread-safe BrainObservationSink recording emitted events."""

    def __init__(self) -> None:
        self.events: List[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        self.events.append(event)

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        return tuple(self.events)


def _selection_events(sink: _CollectorSink) -> Tuple[BrainObservation, ...]:
    return tuple(
        event for event in sink.events if event.boundary == "memory.recall.selection"
    )


def _store_with_lexical_content(
    sink: _CollectorSink,
) -> SQLiteMemoryStoreAdapter:
    store = SQLiteMemoryStoreAdapter.in_memory(observation_sink=sink)
    store.record_episode(
        ClosedEpisode("preference", "preference-key", "2026-08-26", "主人喜欢香菜")
    )
    store.record_episode(
        ClosedEpisode("unrelated", "unrelated-key", "2026-08-26", "主人昨天去公园")
    )
    store.record_episode(
        ClosedEpisode(
            "question-word", "question-word-key", "2026-08-26", "这是一个问题的记录"
        )
    )
    return store


def test_recall_selection_emits_scored_candidates_with_reasons() -> None:
    sink = _CollectorSink()
    store = _store_with_lexical_content(sink)

    store.recall(RecallRequest(text="主人以前喜欢什么？"))

    scored = [
        event.payload
        for event in _selection_events(sink)
        if event.kind == "candidate_scored"
    ]
    assert scored, "expected at least one scored candidate event"
    assert all(isinstance(item, RecallCandidateScored) for item in scored)

    kept_ids = {item.candidate_id for item in scored if item.kept}
    assert "preference" in kept_ids
    for item in scored:
        assert 0.0 <= item.score <= 1.0
        assert item.candidate_kind in ("episode", "node")
        if item.kept:
            assert item.exclusion_reason is None
        else:
            assert item.exclusion_reason is not None
    excluded = [item for item in scored if not item.kept]
    assert excluded, "expected at least one filtered candidate with a reason"
    below_floor = {
        item.candidate_id
        for item in excluded
        if item.exclusion_reason == "score_below_floor"
    }
    assert "unrelated" in below_floor


def test_recall_selection_summary_reports_budget_and_truncation() -> None:
    sink = _CollectorSink()
    store = _store_with_lexical_content(sink)

    store.recall(RecallRequest(text="主人以前喜欢什么？"))

    summaries = [
        event.payload
        for event in _selection_events(sink)
        if event.kind == "selection_summary"
    ]
    assert len(summaries) == 1
    summary = summaries[0]
    assert isinstance(summary, RecallSelectionSummary)
    assert summary.kept >= 1
    assert summary.candidates_seen >= 1
    assert summary.truncated is False
    assert summary.character_budget_limit == RecallRequest().character_limit
    assert summary.character_budget_used > 0


def test_recall_selection_envelopes_are_sequence_ordered_and_causal_free() -> None:
    sink = _CollectorSink()
    store = _store_with_lexical_content(sink)

    store.recall(RecallRequest(text="主人以前喜欢什么？"))
    store.recall(RecallRequest(text="主人喜欢什么？"))

    events = _selection_events(sink)
    assert len(events) >= 2
    sequences = [event.sequence for event in events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)
    for event in events:
        assert event.status.value == "completed"
        assert event.frame_id == ""
        assert event.turn_id == ""
        assert event.captured_at.tzinfo is timezone.utc


def test_blank_recall_emits_no_selection_events() -> None:
    sink = _CollectorSink()
    store = SQLiteMemoryStoreAdapter.in_memory(observation_sink=sink)
    store.record_episode(ClosedEpisode("episode-1", "key-1", "2026-08-26", "花园散步"))

    bundle = store.recall(RecallRequest(text=""))

    assert bundle.episodes == ()
    assert _selection_events(sink) == ()


def test_bind_observation_sink_attaches_once() -> None:
    first = _CollectorSink()
    second = _CollectorSink()
    store = _store_with_lexical_content(first)

    store.bind_observation_sink(second)
    store.recall(RecallRequest(text="主人喜欢什么？"))

    assert _selection_events(second) == ()
    assert _selection_events(first)


def test_recall_without_sink_constructs_no_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError("BrainObservation constructed while no sink is wired")

    monkeypatch.setattr(BrainObservation, "__init__", _forbid_construction)
    store = _store_with_lexical_content(_CollectorSink())
    store._observation_sink = None

    bundle = store.recall(RecallRequest(text="主人以前喜欢什么？"))

    assert [episode.episode_id for episode in bundle.episodes] == ["preference"]
