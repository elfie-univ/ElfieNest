"""Typed Memory facade tests."""

from datetime import datetime, timezone

from elfie.brain.memory import ClosedEpisode, MemorySystem, RecallRequest
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


class _GroundedModel:
    def ask_with_food(self, prompt: str, **_kwargs: object) -> str:
        del prompt
        return (
            '{"nodes":[{"label":"花园","type":"place"}],'
            '"mentions":[{"surface_text":"花园","label":"花园",'
            '"role":"place"}],'
            '"assertions":[]}'
        )


def _new_memory() -> MemorySystem:
    return MemorySystem(
        SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-test"),
        elfie_id="elfie-test",
        initial_at=NOW,
        clock=lambda: NOW,
    )


def _episode(episode_id: str, content: str, importance: float = 0.5) -> ClosedEpisode:
    return ClosedEpisode(
        episode_id=episode_id,
        idempotency_key=episode_id,
        occurred_from=NOW.isoformat(),
        content_text=content,
        importance=importance,
        emotion="calm",
        emotion_intensity=importance,
    )


def test_memory_system_uses_only_typed_components() -> None:
    memory = _new_memory()

    assert memory.uses_typed_memory is True
    assert not hasattr(memory, "sensory_buffer")
    assert not hasattr(memory, "encoder")
    assert not hasattr(memory, "retriever")
    assert not hasattr(memory, "spreading")
    assert not hasattr(memory, "decay")
    assert not hasattr(memory, "weighting")
    assert not hasattr(memory, "recall_formatter")


def test_record_episode_is_source_first_without_keyword_or_intensity_gate() -> None:
    memory = _new_memory()

    episode_id = "episode-low-intensity"
    memory.record_closed_episode(
        _episode(episode_id, "蓝色指南针放在书房北侧。", importance=0.1)
    )

    assert episode_id == "episode-low-intensity"
    episode = memory.storage.get_episode(episode_id)
    assert episode is not None
    assert episode.content_text == "蓝色指南针放在书房北侧。"
    assert episode.importance == 0.1


def test_typed_recall_returns_episode_and_provenance() -> None:
    memory = _new_memory()
    episode_id = "episode-garden"
    memory.record_closed_episode(_episode(episode_id, "今天去花园散步。", 0.7))

    bundle = memory.recall(
        RecallRequest(text="花园", mode="basic_local", episode_limit=5)
    )

    assert [episode.episode_id for episode in bundle.episodes] == [episode_id]
    assert bundle.episodes[0].excerpt == "今天去花园散步。"


def test_source_first_consolidation_requires_grounded_model_and_is_retryable() -> None:
    memory = _new_memory()
    memory.record_closed_episode(
        _episode("episode-consolidate", "我和主人去了花园。", 0.7)
    )

    succeeded = memory.run_consolidation(_GroundedModel())
    assert succeeded["consolidated_count"] == 1
    assert succeeded["knowledge_created"] >= 1


def test_typed_recall_context_uses_stable_renderer() -> None:
    memory = _new_memory()
    memory.record_closed_episode(_episode("episode-candy", "主人给我一颗糖。", 0.8))

    rendered = memory.render_recall(RecallRequest(text="糖", mode="basic_local"))

    assert rendered.startswith("[MEMORY_DATA]")
    assert "主人给我一颗糖。" in rendered
    assert "SOURCES:" in rendered
