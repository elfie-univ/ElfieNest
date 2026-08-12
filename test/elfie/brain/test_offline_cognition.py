from datetime import datetime, timedelta, timezone

from elfie.brain.offline_cognition import (
    OfflineCognitionSystem,
    offline_candidate_to_perception,
)
from elfie.brain.perception_types import InternalPayload, InternalSignal


def test_offline_cognition_only_proposes_while_sleeping_and_settles_after_receipt():
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    pending = ("episode-1", "episode-2")
    calls: list[int] = []
    system = OfflineCognitionSystem(
        pending_episode_ids=lambda _limit: pending,
        consolidate=lambda limit: (
            calls.append(limit)
            or {
                "consolidated_count": limit,
                "knowledge_created": 1,
                "patterns_created": 1,
            }
        ),
        initial_at=now,
    )

    assert system.evaluate(sleeping=False, now=now, blocked=False) is None
    assert calls == []
    candidate = system.evaluate(
        sleeping=True,
        now=now + timedelta(seconds=1),
        blocked=False,
    )
    assert candidate is not None
    assert calls == []
    perception = offline_candidate_to_perception(candidate, elfie_id="elfie-test")
    assert isinstance(perception.payload, InternalPayload)
    assert perception.payload.signal is InternalSignal.OFFLINE_COGNITION

    assert system.settle(
        candidate.candidate_id, now=now + timedelta(seconds=2), success=True
    )
    assert calls == [2]
    snapshot = system.snapshot(now + timedelta(seconds=2))
    assert snapshot.status == "satisfied"
    assert snapshot.last_consolidated_count == 2
    assert snapshot.last_knowledge_created == 1
    assert snapshot.last_patterns_created == 1


def test_offline_cognition_is_blocked_and_does_not_duplicate_pending_candidate():
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    system = OfflineCognitionSystem(
        pending_episode_ids=lambda _limit: ("episode-1",),
        consolidate=lambda _limit: {},
        initial_at=now,
    )

    assert system.evaluate(sleeping=True, now=now, blocked=True) is None
    first = system.evaluate(
        sleeping=True,
        now=now + timedelta(seconds=1),
        blocked=False,
    )
    second = system.evaluate(
        sleeping=True,
        now=now + timedelta(seconds=2),
        blocked=False,
    )
    assert first is not None
    assert second == first
    assert system.snapshot(now + timedelta(seconds=2)).pending_episode_count == 1


def test_offline_cognition_checkpoint_restores_pending_candidate_without_running_work():
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    calls: list[int] = []
    system = OfflineCognitionSystem(
        pending_episode_ids=lambda _limit: ("episode-1",),
        consolidate=lambda limit: calls.append(limit) or {"consolidated_count": limit},
        initial_at=now,
    )
    candidate = system.evaluate(
        sleeping=True, now=now + timedelta(seconds=1), blocked=False
    )
    assert candidate is not None
    checkpoint = system.checkpoint()

    restored = OfflineCognitionSystem(
        pending_episode_ids=lambda _limit: ("episode-1",),
        consolidate=lambda limit: calls.append(limit) or {"consolidated_count": limit},
        initial_at=now,
    )
    restored.restore(checkpoint)
    assert restored.settle(
        candidate.candidate_id, now=now + timedelta(seconds=2), success=True
    )
    assert calls == [1]
