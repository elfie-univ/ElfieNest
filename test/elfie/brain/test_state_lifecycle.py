"""Deterministic candidate/validate/commit/recovery contract tests."""

from datetime import datetime, timezone

import pytest

from elfie.brain.state_lifecycle import (
    StateCandidate,
    StateCommitStatus,
    StateRestoreError,
    VersionedState,
    VersionedStateStore,
)
from elfie.message_types import EventId

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)


def _store() -> VersionedStateStore[str]:
    return VersionedStateStore(
        VersionedState(
            revision=0,
            committed_at=NOW,
            source_event_ids=(),
            causation_id=None,
            value="initial",
        )
    )


def _candidate(
    candidate_id: str, base_revision: int, value: str
) -> StateCandidate[str]:
    return StateCandidate(
        candidate_id=EventId(candidate_id),
        owner="test-owner",
        base_revision=base_revision,
        source_event_ids=(EventId("source-1"),),
        causation_id=EventId("cause-1"),
        created_at=NOW,
        value=value,
    )


def test_candidate_requires_current_revision_and_commits_once() -> None:
    store = _store()
    candidate = _candidate("candidate-1", 0, "next")

    assert store.validate(candidate).status is StateCommitStatus.ACCEPTED
    assert store.snapshot().value == "initial"
    assert store.commit(candidate).status is StateCommitStatus.COMMITTED
    assert store.snapshot().revision == 1
    assert store.snapshot().value == "next"
    assert store.commit(candidate).status is StateCommitStatus.DUPLICATE

    stale = _candidate("candidate-2", 0, "stale")
    assert store.commit(stale).status is StateCommitStatus.STALE
    assert store.snapshot().value == "next"


def test_checkpoint_restores_value_and_idempotency_without_replaying_side_effects() -> (
    None
):
    store = _store()
    candidate = _candidate("candidate-1", 0, "next")
    store.commit(candidate)
    checkpoint = store.checkpoint()

    restored = _store()
    restored.restore(checkpoint)

    assert restored.snapshot().revision == 1
    assert restored.snapshot().value == "next"
    assert restored.commit(candidate).status is StateCommitStatus.DUPLICATE

    with pytest.raises(StateRestoreError):
        restored.restore(
            checkpoint.__class__(
                revision=0,
                committed_at=NOW,
                source_event_ids=(),
                causation_id=None,
                value="older",
                committed_candidate_ids=(),
            )
        )
