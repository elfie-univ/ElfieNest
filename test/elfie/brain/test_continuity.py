"""Stage 4C continuity and cognitive-budget boundaries."""

from datetime import datetime, timezone

import pytest

from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.memory.memory_records import ClosedEpisode
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.state_lifecycle import StateRestoreError
from elfie.message_types import EventId
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)


def test_emotion_checkpoint_restores_deduplication_and_rejects_stale_state() -> None:
    emotion = EmotionSystem(clock=lambda: 0.0)
    stimulus = EmotionStimulusEvent(
        event_id=EventId("emotion-source-1"),
        emotion=EmotionType.FEAR,
        intensity=0.8,
        source=StimulusSource.PHYSICAL,
    )
    emotion.apply_stimulus(stimulus)
    checkpoint = emotion.checkpoint()

    emotion.update_emotion("fear", 10.0)
    with pytest.raises(StateRestoreError):
        emotion.restore(checkpoint)

    restored = EmotionSystem(clock=lambda: 0.0)
    restored.restore(checkpoint)
    before = restored.snapshot(0.0)
    restored.apply_stimulus(stimulus)

    assert restored.snapshot(0.0) == before
    assert restored.snapshot(0.0).source_event_ids == (EventId("emotion-source-1"),)


def test_energy_checkpoint_and_cognitive_mode_boundary() -> None:
    energy = EnergySystem(clock=lambda: 0.0)
    checkpoint = energy.checkpoint()
    assert energy.snapshot(0.0).cognitive_mode == "long"
    assert energy.can_start_long_reasoning() is True

    energy.advance_to(10.0)
    with pytest.raises(StateRestoreError):
        energy.restore(checkpoint)

    emergency = EnergySystem(
        {"limits": {"energy": {"initial_value": 5.0}}},
        clock=lambda: 0.0,
    )
    snapshot = emergency.snapshot(0.0)
    assert snapshot.cognitive_mode == "emergency"
    assert snapshot.long_reasoning_allowed is False
    assert emergency.can_start_long_reasoning() is False


def test_memory_checkpoint_tracks_durable_counts_and_rejects_missing_or_stale_state() -> (
    None
):
    store = SQLiteMemoryStoreAdapter.in_memory()
    memory = MemorySystem(
        storage=store,
        clock=lambda: NOW,
        initial_at=NOW,
    )
    memory.record_closed_episode(
        ClosedEpisode(
            episode_id="continuity-episode-1",
            idempotency_key="continuity-episode-1",
            occurred_from=NOW.isoformat(),
            content_text="主人给了我一颗糖",
            emotion="happiness",
            emotion_intensity=0.8,
            importance=0.8,
            source_event_ids=("memory-source-1",),
        )
    )
    checkpoint = memory.checkpoint()
    assert memory.snapshot(NOW).revision == checkpoint.revision
    assert memory.snapshot(NOW).episodic_count == 1

    restored = MemorySystem(
        storage=store,
        clock=lambda: NOW,
        initial_at=NOW,
    )
    restored.restore(checkpoint)
    assert restored.snapshot(NOW).revision == checkpoint.revision
    assert restored.snapshot(NOW).total_count >= checkpoint.value.total_count

    memory.record_closed_episode(
        ClosedEpisode(
            episode_id="continuity-episode-2",
            idempotency_key="continuity-episode-2",
            occurred_from=NOW.isoformat(),
            content_text="主人又给了我一颗糖",
            emotion="happiness",
            emotion_intensity=0.8,
            importance=0.8,
        )
    )
    with pytest.raises(StateRestoreError):
        memory.restore(checkpoint)
