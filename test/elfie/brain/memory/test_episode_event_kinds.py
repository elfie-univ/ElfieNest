"""The durable Episode experience-kind vocabulary is controlled."""

from __future__ import annotations

import pytest

from elfie.brain.memory.memory_records import ClosedEpisode
from infrastructure.persistence.memory.sqlite_memory_store import (
    SQLiteMemoryStoreAdapter,
)


def _episode(event_kind: str) -> ClosedEpisode:
    return ClosedEpisode(
        episode_id="episode-kind",
        idempotency_key="episode-kind-key",
        occurred_from="2026-09-01T00:00:00+00:00",
        content_text="一段有来源的经历",
        event_kind=event_kind,
    )


@pytest.mark.parametrize(
    "event_kind",
    (
        "conversation",
        "activity",
        "outing",
        "learning",
        "life_event",
        "observation",
        "reflection",
        "unclassified",
    ),
)
def test_episode_accepts_only_registered_experience_kinds(event_kind: str) -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        assert store.record_episode(_episode(event_kind)).episode_id == "episode-kind"


@pytest.mark.parametrize(
    "event_kind",
    (
        "interaction",
        "completed_interaction",
        "genesis_knowledge_episode",
        "genesis_personal_episode",
        "initialization",
        "reset",
        "consolidation_failed",
    ),
)
def test_episode_rejects_source_and_process_labels_as_experience_kinds(
    event_kind: str,
) -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        with pytest.raises(ValueError, match="unsupported Episode event_kind"):
            store.record_episode(_episode(event_kind))
