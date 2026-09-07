"""Memory-encode observations on the MemorySystem candidate→commit boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

import pytest

from elfie.brain.memory.candidates import EpisodicMemoryCandidate
from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    MemoryUseProposal,
    QualifiedReinforcementReceipt,
    RecallRequest,
)
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.memory.observation_payloads import (
    MemoryEncodeCandidate,
    MemoryEncodeCommit,
    MemoryReinforcementApplied,
    MemoryUseProposalRecorded,
)
from elfie.brain.observation import BrainObservation
from elfie.message_types import EventId
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc)
EPISODE_ID = "memory-episode:memory-interaction:receipt-1"


class _CollectorSink:
    """Minimal thread-safe BrainObservationSink recording emitted events."""

    def __init__(self) -> None:
        self.events: List[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        self.events.append(event)

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        return tuple(self.events)


def _encode_events(sink: _CollectorSink) -> Tuple[BrainObservation, ...]:
    return tuple(event for event in sink.events if event.boundary == "memory.encode")


def _candidate(
    candidate_id: str = "memory-interaction:receipt-1",
    *,
    base_revision: int = 0,
) -> EpisodicMemoryCandidate:
    return EpisodicMemoryCandidate(
        candidate_id=EventId(candidate_id),
        base_revision=base_revision,
        content="主人问候我，我完成了回复。",
        emotion="calm",
        intensity=0.0,
        stimulus="completed-owner-interaction:conversation-1",
        source_event_ids=(EventId("owner-1"), EventId("reply-1")),
        created_at=NOW,
    )


def _memory(sink: _CollectorSink) -> MemorySystem:
    return MemorySystem(
        SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-encode"),
        elfie_id="elfie-encode",
        initial_at=NOW,
        clock=lambda: NOW,
        observation_sink=sink,
    )


def test_commit_episode_candidate_emits_candidate_then_commit_receipt() -> None:
    sink = _CollectorSink()
    memory = _memory(sink)

    receipt = memory.commit_episode_candidate(_candidate())

    assert receipt.status.value == "committed"
    committed = _encode_events(sink)
    assert [event.kind for event in committed] == [
        "encode_candidate",
        "encode_commit",
    ]
    candidate_payload = committed[0].payload
    assert isinstance(candidate_payload, MemoryEncodeCandidate)
    assert candidate_payload.candidate_id == "memory-interaction:receipt-1"
    assert candidate_payload.base_revision == 0
    assert candidate_payload.source_event_ids == ("owner-1", "reply-1")
    assert candidate_payload.emotion == "calm"
    assert candidate_payload.intensity == 0.0
    assert candidate_payload.content_chars == len("主人问候我，我完成了回复。")

    commit_payload = committed[1].payload
    assert isinstance(commit_payload, MemoryEncodeCommit)
    assert commit_payload.status == "committed"
    assert commit_payload.reason is None
    assert commit_payload.episode_id == EPISODE_ID
    assert commit_payload.revision_before == 0
    assert commit_payload.revision_after == 1


def test_duplicate_and_stale_candidates_emit_rejected_receipts() -> None:
    sink = _CollectorSink()
    memory = _memory(sink)
    assert memory.commit_episode_candidate(_candidate()).status.value == "committed"

    duplicate = memory.commit_episode_candidate(_candidate())
    stale = memory.commit_episode_candidate(
        _candidate("memory-interaction:receipt-2", base_revision=0)
    )

    assert duplicate.status.value == "duplicate"
    assert stale.status.value == "stale"
    commits = [
        event.payload for event in _encode_events(sink) if event.kind == "encode_commit"
    ]
    assert len(commits) == 3
    duplicate_payload = commits[1]
    stale_payload = commits[2]
    assert isinstance(duplicate_payload, MemoryEncodeCommit)
    assert isinstance(stale_payload, MemoryEncodeCommit)
    assert duplicate_payload.status == "duplicate"
    assert duplicate_payload.reason == "candidate_already_committed"
    assert duplicate_payload.episode_id is None
    assert duplicate_payload.revision_before == 1
    assert duplicate_payload.revision_after == 1
    assert stale_payload.status == "stale"
    assert stale_payload.reason == "base_revision_mismatch"
    assert stale_payload.episode_id is None


def test_use_proposal_and_reinforcement_emit_outcome_events() -> None:
    sink = _CollectorSink()
    memory = _memory(sink)
    memory.record_closed_episode(
        ClosedEpisode(
            "episode-garden", "garden-key", NOW.isoformat(), "今天去花园散步。"
        )
    )
    bundle = memory.recall(
        RecallRequest(text="花园", mode="basic_local", episode_limit=5)
    )
    proposal = MemoryUseProposal(
        proposal_id="proposal-1",
        recall_revision=bundle.recall_revision,
        occurred_at=NOW.isoformat(),
        target_kind="episode",
        target_ids=("episode-garden",),
    )

    assert memory.submit_memory_use_proposal(proposal, bundle) is True
    assert memory.submit_memory_use_proposal(proposal, bundle) is False
    stale_proposal = MemoryUseProposal(
        proposal_id="proposal-2",
        recall_revision=bundle.recall_revision + 5,
        occurred_at=NOW.isoformat(),
        target_kind="episode",
        target_ids=("episode-garden",),
    )
    with pytest.raises(ValueError, match="memory-use proposal revision is stale"):
        memory.submit_memory_use_proposal(stale_proposal, bundle)

    recorded = [
        event.payload
        for event in _encode_events(sink)
        if event.kind == "use_proposal_recorded"
    ]
    assert len(recorded) == 3
    assert all(isinstance(item, MemoryUseProposalRecorded) for item in recorded)
    assert [item.accepted for item in recorded] == [True, False, False]
    assert recorded[0].reason is None
    assert recorded[1].reason == "proposal_already_submitted"
    assert recorded[2].reason == "memory-use proposal revision is stale"

    reinforcement = QualifiedReinforcementReceipt(
        event_id="reinforcement-1",
        target_kind="episode",
        target_id="episode-garden",
        occurred_at=NOW.isoformat(),
        outcome_kind="explicit_confirmation",
        source_ref="source-1",
        recall_revision=bundle.recall_revision,
        proposal_id="proposal-1",
    )
    revision_before = memory.revision
    assert memory.consume_reinforcement_receipt(reinforcement) is True

    applied = [
        event.payload
        for event in _encode_events(sink)
        if event.kind == "reinforcement_applied"
    ]
    assert len(applied) == 1
    payload = applied[0]
    assert isinstance(payload, MemoryReinforcementApplied)
    assert payload.accepted is True
    assert payload.reason is None
    assert payload.event_id == "reinforcement-1"
    assert payload.proposal_id == "proposal-1"
    assert payload.target_id == "episode-garden"
    assert payload.revision_before == revision_before
    assert payload.revision_after == revision_before + 1


def test_encode_without_sink_constructs_no_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError("BrainObservation constructed while no sink is wired")

    monkeypatch.setattr(BrainObservation, "__init__", _forbid_construction)
    memory = MemorySystem(
        SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-encode"),
        elfie_id="elfie-encode",
        initial_at=NOW,
        clock=lambda: NOW,
    )

    first = memory.commit_episode_candidate(_candidate())
    duplicate = memory.commit_episode_candidate(_candidate())
    stale = memory.commit_episode_candidate(
        _candidate("memory-interaction:receipt-2", base_revision=0)
    )

    assert first.status.value == "committed"
    assert duplicate.status.value == "duplicate"
    assert stale.status.value == "stale"


def test_encode_envelopes_are_sequence_ordered() -> None:
    sink = _CollectorSink()
    memory = _memory(sink)
    memory.commit_episode_candidate(_candidate())
    memory.commit_episode_candidate(_candidate())

    events = _encode_events(sink)
    sequences = [event.sequence for event in events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)
    for event in events:
        assert event.boundary == "memory.encode"
        assert event.captured_at.tzinfo is timezone.utc
