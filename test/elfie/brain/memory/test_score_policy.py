from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from elfie.brain.memory.score_policy import (
    EvidenceContribution,
    ImportanceEvent,
    MemoryScorePolicy,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_v2_freshness_golden_vectors() -> None:
    assert MemoryScorePolicy.freshness(NOW, NOW, 7.0) == 1.0
    assert MemoryScorePolicy.freshness(
        NOW + timedelta(days=3.5), NOW, 7.0
    ) == pytest.approx(0.402504156, rel=1e-7)
    assert MemoryScorePolicy.freshness(
        NOW + timedelta(days=7), NOW, 7.0
    ) == pytest.approx(0.1)


def test_freshness_clamps_small_future_clock_delta_and_rejects_invalid_span() -> None:
    assert MemoryScorePolicy.freshness(NOW, NOW + timedelta(seconds=1), 7.0) == 1.0
    with pytest.raises(ValueError):
        MemoryScorePolicy.freshness(NOW, NOW, 0.0)
    with pytest.raises(ValueError):
        MemoryScorePolicy.freshness(NOW, NOW, 36_501.0)


def test_reinforcement_uses_event_time_and_has_expected_growth() -> None:
    unchanged = MemoryScorePolicy.reinforce(
        retention_days=7.0,
        last_reinforced_at=NOW,
        occurred_at=NOW,
    )
    assert unchanged is not None
    assert unchanged.retention_days == pytest.approx(7.0)

    at_half = MemoryScorePolicy.reinforce(
        retention_days=7.0,
        last_reinforced_at=NOW,
        occurred_at=NOW + timedelta(days=3.5),
    )
    assert at_half is not None
    assert at_half.retention_days == pytest.approx(10.085196283, rel=1e-7)
    assert at_half.last_reinforced_at == NOW + timedelta(days=3.5)

    at_boundary = MemoryScorePolicy.reinforce(
        retention_days=7.0,
        last_reinforced_at=NOW,
        occurred_at=NOW + timedelta(days=7),
    )
    assert at_boundary is not None
    assert at_boundary.retention_days == pytest.approx(14.0)

    expired = MemoryScorePolicy.reinforce(
        retention_days=7.0,
        last_reinforced_at=NOW,
        occurred_at=NOW + timedelta(days=8),
    )
    assert expired is None


def test_next_review_inverse_vectors() -> None:
    for threshold, expected_ratio in (
        (0.4, 0.502008485),
        (0.2, 0.732057485),
        (0.1, 1.0),
        (0.01, 2.514986442),
    ):
        due = MemoryScorePolicy.next_review_at(NOW, 7.0, threshold)
        assert (due - NOW).total_seconds() / 86_400 == pytest.approx(
            7.0 * expected_ratio, rel=1e-7
        )


def test_importance_moves_toward_policy_target_and_never_overshoots() -> None:
    assert MemoryScorePolicy.apply_importance(
        current=0.2, direction="raise", event_class="meaningful"
    ) == pytest.approx(0.28)
    assert MemoryScorePolicy.apply_importance(
        current=0.8, direction="lower", event_class="major-lower"
    ) == pytest.approx(0.45)
    assert MemoryScorePolicy.apply_importance(
        current=0.99, direction="raise", event_class="routine"
    ) == pytest.approx(0.99)
    with pytest.raises(ValueError):
        MemoryScorePolicy.apply_importance(
            current=0.5, direction="raise", event_class="not-a-class"
        )


def _importance_event(
    event_id: str,
    event_class: str,
    *,
    direction: str = "raise",
    hours: int = 0,
    episode: Optional[str] = None,
) -> ImportanceEvent:
    return ImportanceEvent(
        event_id=event_id,
        target_kind="node",
        target_id="owner",
        direction=direction,  # type: ignore[arg-type]
        event_class=event_class,
        occurred_at=NOW + timedelta(hours=hours),
        source_episode_id=episode or event_id,
    )


def test_importance_aggregation_deduplicates_and_separates_directions() -> None:
    events = (
        _importance_event("routine-a", "routine", episode="ep-a"),
        _importance_event("meaningful-a", "meaningful", hours=1, episode="ep-b"),
        _importance_event("major-a", "major", hours=2, episode="ep-c"),
        _importance_event("duplicate", "routine", hours=3, episode="ep-a"),
        _importance_event(
            "lower-a",
            "ordinary-lower",
            direction="lower",
            hours=4,
            episode="ep-d",
        ),
        _importance_event(
            "new-window",
            "core",
            hours=25,
            episode="ep-e",
        ),
    )
    aggregates = MemoryScorePolicy.aggregate_importance_events(events)
    assert [(item.direction, item.event_class) for item in aggregates] == [
        ("raise", "major"),
        ("lower", "ordinary-lower"),
        ("raise", "core"),
    ]
    assert MemoryScorePolicy.fold_importance(
        initial=0.5, events=events
    ) == pytest.approx(0.7709375)


def test_importance_events_without_episode_sources_remain_independent() -> None:
    events = (
        ImportanceEvent(
            "external-a",
            "node",
            "owner",
            "raise",
            "meaningful",
            NOW,
            source_episode_id=None,
        ),
        ImportanceEvent(
            "external-b",
            "node",
            "owner",
            "raise",
            "meaningful",
            NOW + timedelta(hours=25),
            source_episode_id=None,
        ),
    )
    aggregates = MemoryScorePolicy.aggregate_importance_events(events)
    assert tuple(item.event_id for item in aggregates) == (
        "external-a",
        "external-b",
    )
    assert MemoryScorePolicy.fold_importance(
        initial=0.2, events=events
    ) == pytest.approx(0.344)


def test_confidence_uses_unique_independence_groups_and_ignores_context() -> None:
    contributions = (
        EvidenceContribution("e1", "source-a", "supports", 0.9),
        EvidenceContribution("e1-copy", "source-a", "supports", 0.4),
        EvidenceContribution("e2", "source-b", "supports", 0.7),
        EvidenceContribution("e3", "source-a", "contradicts", 0.8),
        EvidenceContribution("e4", "source-c", "context", 10.0),
    )
    confidence = MemoryScorePolicy.confidence_from_evidence(
        initial_confidence=0.5,
        prior_weight=1.0,
        contributions=contributions,
    )
    assert confidence == pytest.approx((0.5 + 0.9 + 0.7) / (1 + 0.9 + 0.7 + 0.8))


def test_recall_score_keeps_episode_without_confidence_and_applies_formula() -> None:
    episode = MemoryScorePolicy.recall_score(
        relevance=0.8,
        freshness=0.4,
        importance=0.6,
        confidence=None,
    )
    assertion = MemoryScorePolicy.recall_score(
        relevance=0.8,
        freshness=0.4,
        importance=0.6,
        confidence=0.8,
    )
    assert episode.confidence is None
    assert episode.rank == pytest.approx(0.8 * (0.65 * 0.4 + 0.35 * 0.6))
    assert assertion.rank == pytest.approx(episode.rank * (0.25 + 0.75 * 0.8))


def test_logical_forgetting_requires_all_conditions() -> None:
    assert MemoryScorePolicy.can_logically_forget(
        freshness=0.01,
        importance=0.1,
        archived_days=90,
        dependency_safe=True,
    )
    assert not MemoryScorePolicy.can_logically_forget(
        freshness=0.01,
        importance=0.1,
        archived_days=89,
        dependency_safe=True,
    )
