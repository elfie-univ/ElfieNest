from __future__ import annotations

from pathlib import Path

from app.features.elfie_profile.private_cognition_focus import recent_topics
from app.features.elfie_profile.private_cognition_projection import (
    project_private_cognition,
)
from app.infrastructure.persistence.elfie_cognition_reader import (
    CognitionEvent,
    read_elfie_cognition,
)
from elfie.brain.memory.knowledge_store import KnowledgeStore
from elfie.brain.memory.node_types import MemoryNode


def _seed_store(path: Path) -> None:
    with KnowledgeStore(path) as store:
        store.add_node(
            MemoryNode(
                id="core_world",
                type="core",
                content="大多数时候世界是安全的。",
                metadata={"core_key": "world"},
            )
        )
        store.add_node(
            MemoryNode(
                id="adoption",
                type="episodic",
                content="被主人领养，搬进了新的家。",
                metadata={
                    "timestamp": "2026-06-30T08:00:00Z",
                    "major_event": True,
                    "importance": 0.95,
                    "title": "被领养",
                    "changed": "从此有了自己的家",
                    "people": ["主人"],
                    "topics": [{"label": "新家", "category": "place"}],
                },
            )
        )
        store.add_node(
            MemoryNode(
                id="recent_walk",
                type="episodic",
                content="和主人去公园散步，发现了安静的小路。",
                metadata={
                    "timestamp": "2026-08-01T08:00:00Z",
                    "importance": 0.7,
                    "topics": ["公园", "散步", "小路"],
                },
            )
        )
        store.add_node(
            MemoryNode(
                id="ordinary",
                type="episodic",
                content="今天吃了一顿普通的饭。",
                metadata={
                    "timestamp": "2026-08-02T08:00:00Z",
                    "importance": 0.1,
                },
            )
        )
        store.add_node(
            MemoryNode(
                id="owner",
                type="entity",
                content="主人",
                metadata={
                    "entity_type": "person",
                    "relationship": "主人",
                    "relation_kind": "owner",
                    "importance": 1.0,
                },
            )
        )
        store.add_node(
            MemoryNode(
                id="friend_elfie",
                type="entity",
                content="月光",
                metadata={
                    "entity_type": "elfie",
                    "relationship": "朋友",
                    "relation_kind": "friend",
                    "importance": 0.75,
                },
            )
        )
        store.add_node(
            MemoryNode(
                id="source_walk",
                type="knowledge",
                content="和主人一起散步",
                metadata={"kind": "source", "importance": 0.7},
            )
        )
        store.add_node(
            MemoryNode(
                id="knowledge_quiet",
                type="knowledge",
                content="安静的小路更适合观察",
                metadata={"kind": "knowledge", "importance": 0.8},
            )
        )
        store.add_node(
            MemoryNode(
                id="belief_safe",
                type="knowledge",
                content="安静的地方让我安心",
                metadata={"kind": "belief", "importance": 0.9},
            )
        )
        store.add_edge("source_walk", "knowledge_quiet", "derived_from", 0.8)
        store.add_edge("knowledge_quiet", "belief_safe", "supports", 0.9)


def test_projection_matches_the_approved_five_module_contract_deterministically(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite"
    _seed_store(path)
    first = project_private_cognition(
        read_elfie_cognition(path), elfie_id="12345678", elfie_name="星尘"
    )
    second = project_private_cognition(
        read_elfie_cognition(path), elfie_id="12345678", elfie_name="星尘"
    )

    assert first == second
    assert first["status"] == "ready"
    assert set(first) == {
        "status",
        "recent_focus",
        "important_experiences",
        "relationship_world",
        "world_understanding",
        "knowledge_beliefs",
    }
    assert len(first["recent_focus"]["topics"]) <= 20
    assert first["recent_focus"]["topics"][0]["label"] == "公园"
    assert [entry["id"] for entry in first["important_experiences"]["entries"]] == [
        "adoption"
    ]
    assert [node["kind"] for node in first["relationship_world"]["nodes"]] == [
        "self",
        "human",
        "elfie",
    ]
    assert len(first["relationship_world"]["nodes"]) <= 20
    assert [ring["key"] for ring in first["world_understanding"]["rings"]] == [
        "self",
        "family",
        "nest",
        "society",
        "outside",
    ]
    assert first["world_understanding"]["summary"] == "大多数时候世界是安全的。"
    assert {node["kind"] for node in first["knowledge_beliefs"]["nodes"]} == {
        "source",
        "knowledge",
        "belief",
    }
    assert len(first["knowledge_beliefs"]["nodes"]) <= 10


def test_projection_degrades_without_private_store(tmp_path: Path) -> None:
    result = project_private_cognition(
        read_elfie_cognition(tmp_path / "missing.sqlite"),
        elfie_id="12345678",
        elfie_name="星尘",
    )

    assert result["status"] == "empty"
    assert result["recent_focus"]["topics"] == []
    assert result["important_experiences"]["entries"] == []
    assert result["relationship_world"]["nodes"] == [
        {"id": "self", "label": "星尘", "kind": "self", "weight": 1.0}
    ]


def test_recent_topics_keeps_fifty_stable_topics_for_the_word_cloud() -> None:
    events = tuple(
        CognitionEvent(
            id=f"event-{index:02d}",
            occurred_at="2026-08-02T08:00:00Z",
            event_type="observation",
            description=f"观察主题{index:02d}",
            importance=index / 60,
            metadata={"topics": [f"主题{index:02d}"]},
        )
        for index in range(55)
    )

    topics = recent_topics(events, "星尘")

    assert len(topics) == 50
    assert topics[0]["label"] == "主题54"
    assert topics[-1]["label"] == "主题05"
