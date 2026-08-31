"""Selfhood is no longer a Memory-owned narrative projection.

The old ``MemorySelfNarrativeProjection`` tests intentionally disappeared with
the production type. These focused checks keep the ownership boundary
executable: Memory stores ordinary evidence and never creates a second
self-story.
"""

from elfie.brain.memory import MemorySystem
from test.elfie.brain.memory.fake_store import FakeMemoryStore


def test_memory_does_not_construct_or_expose_a_self_narrative() -> None:
    memory = MemorySystem(storage=FakeMemoryStore.in_memory())

    assert not hasattr(memory, "self_narrative")
    assert not hasattr(memory, "get_self_narrative")
    assert memory.storage.count_nodes("core") == 0


def test_memory_recall_contains_only_ordinary_evidence() -> None:
    memory = MemorySystem(storage=FakeMemoryStore.in_memory())
    memory.record_episode(
        content="主人带我去花园散步",
        emotion="happy",
        intensity=80.0,
    )

    context = memory.recall_context(
        query="花园",
        emotion="happy",
        intensity=0.8,
        entities=["花园"],
        current_time="2026-06-06T10:00:00",
    )

    assert "核心认知" not in context
    assert "花园" in context
