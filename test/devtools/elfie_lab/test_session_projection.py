"""Characterization and behavior tests for Elfie Lab memory projections."""

from math import isfinite
from types import SimpleNamespace

import pytest

from devtools.elfie_lab.schemas import ElfieSpec
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.session_projection import _memory_cognition_projection
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie.brain.memory.memory_records import MemoryInspectionSnapshot
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.devtools.elfie_lab.projection_test_support import add_edge, add_node


@pytest.fixture
def projection_subject():
    storage = SQLiteMemoryStoreAdapter.in_memory()

    def inspection_snapshot(**limits):
        return MemoryInspectionSnapshot(
            episodes=storage.list_episodes(limit=limits.get("episode_limit", 1000)),
            nodes=storage.list_graph_nodes(limit=limits.get("node_limit", 1000)),
            assertions=storage.list_graph_assertions(
                limit=limits.get("assertion_limit", 800)
            ),
        )

    memory = SimpleNamespace(memory_inspection_snapshot=inspection_snapshot)
    yield (
        SimpleNamespace(_memory=memory),
        ElfieSpec(elfie_id="test", name="艾菲"),
        storage,
    )
    storage.close()


def test_low_data_projection_preserves_existing_payload_shape(tmp_path) -> None:
    # Given
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("低数据精灵")
    session = ElfieLabSession(spec, storage)

    try:
        # When
        projection = session.profile()["memory_cognition"]
    finally:
        session.close()

    # Then
    assert set(projection) == {
        "important_events",
        "knowledge",
        "relations",
        "topics",
        "world_model",
        "world_understanding",
    }
    # A newly created Lab Elfie already has the required Genesis memory seed;
    # low-data here means no user-added records, not an empty memory store.
    assert projection["topics"]
    assert projection["important_events"]
    assert isinstance(projection["relations"]["nodes"], list)
    assert isinstance(projection["relations"]["links"], list)
    assert isinstance(projection["knowledge"]["nodes"], list)
    assert isinstance(projection["knowledge"]["links"], list)
    assert any(node["id"] == "self" for node in projection["relations"]["nodes"])
    assert len(projection["world_model"]["rings"]) == 5


def test_projection_caps_collections_and_is_deterministic(projection_subject) -> None:
    # Given
    elfie, spec, storage = projection_subject
    for index in reversed(range(25)):
        add_node(
            storage,
            f"entity_{index:02d}",
            "entity",
            f"人物{index:02d}",
            {"importance": index / 24, "entity_type": "human"},
        )
        add_node(
            storage,
            f"knowledge_{index:02d}",
            "knowledge",
            f"知识{index:02d}",
            {"importance": index / 24},
        )
        add_node(
            storage,
            f"episode_{index:02d}",
            "episodic",
            f"topic{index:02d}",
            {"timestamp": f"2026-07-{index + 1:02d}", "importance": index / 24},
        )

    # When
    first = _memory_cognition_projection(elfie, spec)
    second = _memory_cognition_projection(elfie, spec)

    # Then
    assert first == second
    assert len(first["topics"]) == 20
    assert len(first["important_events"]) == 20
    assert len(first["relations"]["nodes"]) == 20
    assert len(first["knowledge"]["nodes"]) == 20
    assert first["important_events"][0]["id"] == "episode_24"
    assert set(first["topics"][0]) == {"label", "weight", "category"}


def test_projection_normalizes_malformed_numeric_metadata(projection_subject) -> None:
    # Given
    elfie, spec, storage = projection_subject
    # SQLite's JSON validity constraint rejects non-finite float literals
    # before the projection can inspect them. ``None`` keeps the malformed
    # numeric case JSON-safe while still exercising the projection fallback.
    raw_weights = [None, "heavy", 2.4, -3]
    for index, raw_weight in enumerate(raw_weights):
        add_node(
            storage,
            f"entity_{index}",
            "entity",
            f"人物{index}",
            {"importance": raw_weight, "entity_type": "human"},
        )
        add_node(
            storage,
            f"knowledge_{index}",
            "knowledge",
            f"知识{index}",
            {"importance": raw_weight, "confidence": raw_weight},
        )

    # When
    projection = _memory_cognition_projection(elfie, spec)

    # Then
    numeric_values = [
        node[field]
        for graph_name in ("relations", "knowledge")
        for node in projection[graph_name]["nodes"]
        for field in (
            ("weight", "confidence") if graph_name == "knowledge" else ("weight",)
        )
    ]
    assert all(isfinite(value) and 0.0 <= value <= 1.0 for value in numeric_values)
    assert set(projection["knowledge"]["nodes"][0]) == {
        "id",
        "label",
        "kind",
        "weight",
        "confidence",
        "source_event_ids",
    }


def test_knowledge_links_preserve_stored_direction(projection_subject) -> None:
    # Given
    elfie, spec, storage = projection_subject
    add_node(storage, "premise", "knowledge", "天空有云")
    add_node(storage, "conclusion", "knowledge", "可能会下雨")
    add_edge(storage, "premise", "conclusion", "supports", 0.8)

    # When
    links = _memory_cognition_projection(elfie, spec)["knowledge"]["links"]

    # Then
    assert links == [
        {
            "source": "premise",
            "target": "conclusion",
            "label": "supports",
            "relation_kind": "supports",
            "weight": 0.8,
        }
    ]


def test_self_relation_requires_and_uses_explicit_entity_metadata(
    projection_subject,
) -> None:
    # Given
    elfie, spec, storage = projection_subject
    add_node(storage, "owner", "entity", "小真", {"entity_type": "human"})
    add_node(
        storage,
        "friend",
        "entity",
        "阿沐",
        {
            "entity_type": "elfie",
            "relationship": "朋友",
            "relation_kind": "friend",
            "importance": 0.9,
        },
    )

    # When
    relations = _memory_cognition_projection(elfie, spec)["relations"]

    # Then
    assert relations["links"] == [
        {
            "source": "self",
            "target": "friend",
            "label": "朋友",
            "relation_kind": "friend",
            "weight": 0.9,
        }
    ]
    assert {node["id"]: node["kind"] for node in relations["nodes"]} == {
        "self": "self",
        "friend": "elfie",
        "owner": "human",
    }


def test_relationship_projection_keeps_self_and_cross_entity_links(
    projection_subject,
) -> None:
    # Given
    elfie, spec, storage = projection_subject
    for index in range(19):
        add_node(
            storage,
            f"entity_{index:02d}",
            "entity",
            f"人物{index:02d}",
            {
                "entity_type": "human",
                "relationship": "认识",
                "relation_kind": "acquaintance",
                "importance": 1 - index / 20,
            },
        )
    for index in range(12):
        add_edge(
            storage,
            f"entity_{index:02d}",
            f"entity_{index + 1:02d}",
            "family" if index % 2 == 0 else "friend",
            0.8,
        )

    # When
    links = _memory_cognition_projection(elfie, spec)["relations"]["links"]

    # Then
    assert len(links) == 31
    assert sum(link["source"] == "self" for link in links) == 19
    assert sum(link["source"] != "self" for link in links) == 12
    assert {link["label"] for link in links if link["source"] != "self"} == {
        "家人",
        "朋友",
    }


def test_important_event_uses_importance_then_intensity_fallback(
    projection_subject,
) -> None:
    # Given
    elfie, spec, storage = projection_subject
    add_node(
        storage,
        "event_explicit",
        "episodic",
        "认识了阿沐",
        {
            "timestamp": "2026-07-28T10:00:00Z",
            "emotion": "joy",
            "importance": 0.7,
            "emotion_intensity": 0.2,
            "people": ["阿沐"],
            "changed": True,
        },
    )
    add_node(
        storage,
        "event_fallback",
        "episodic",
        "听见雷声",
        {"timestamp": "2026-07-29T10:00:00Z", "emotion_intensity": 0.6},
    )

    # When
    events = _memory_cognition_projection(elfie, spec)["important_events"]

    # Then
    assert events == [
        {
            "id": "event_fallback",
            "content": "听见雷声",
            "timestamp": "2026-07-29T10:00:00Z",
            "emotion": "",
            "importance": 0.6,
            "people": [],
            "changed": "",
        },
        {
            "id": "event_explicit",
            "content": "认识了阿沐",
            "timestamp": "2026-07-28T10:00:00Z",
            "emotion": "joy",
            "importance": 0.7,
            "people": ["阿沐"],
            "changed": "",
        },
    ]


def test_event_changed_preserves_text_and_rejects_non_strings(
    projection_subject,
) -> None:
    # Given
    elfie, spec, storage = projection_subject
    add_node(storage, "text", "episodic", "交到朋友", {"changed": "更愿意信任伙伴"})
    add_node(storage, "boolean", "episodic", "旧布尔值", {"changed": True})
    add_node(storage, "missing", "episodic", "普通一天")

    # When
    events = _memory_cognition_projection(elfie, spec)["important_events"]

    # Then
    assert {event["id"]: event["changed"] for event in events} == {
        "text": "更愿意信任伙伴",
        "boolean": "",
        "missing": "",
    }


def test_topic_categories_use_metadata_then_deterministic_keywords(
    projection_subject,
) -> None:
    # Given
    elfie, spec, storage = projection_subject
    samples = [
        ("owner", "主人", {}),
        ("park", "公园", {}),
        ("joy", "开心", {}),
        ("walk", "散步", {}),
        ("explicit", "Comet", {"topic_categories": {"Comet": "person"}}),
        ("default", "cloud", {}),
    ]
    for node_id, content, metadata in samples:
        add_node(storage, node_id, "episodic", content, metadata)

    # When
    topics = _memory_cognition_projection(elfie, spec)["topics"]

    # Then
    assert {topic["label"]: topic["category"] for topic in topics} == {
        "主人": "person",
        "公园": "place",
        "开心": "emotion",
        "散步": "activity",
        "Comet": "person",
        "cloud": "activity",
    }


def test_world_model_caps_nodes_globally_across_rings(projection_subject) -> None:
    # Given
    elfie, spec, storage = projection_subject
    ring_kinds = ("self", "family", "nest", "society", "outside")
    for index in range(25):
        add_node(
            storage,
            f"world_{index:02d}",
            "knowledge",
            f"世界认知{index:02d}",
            {"world_ring": ring_kinds[index % 5], "importance": index / 24},
        )

    # When
    rings = _memory_cognition_projection(elfie, spec)["world_model"]["rings"]

    # Then
    assert [ring["kind"] for ring in rings] == list(ring_kinds)
    assert sum(len(ring["nodes"]) for ring in rings) == 20


def test_world_model_has_fixed_five_rings_without_fabricated_nodes(
    projection_subject,
) -> None:
    # Given
    elfie, spec, storage = projection_subject
    add_node(
        storage,
        "world",
        "knowledge",
        "世界仍在展开。",
        {"core_key": "world"},
    )
    add_node(
        storage,
        "home_rule",
        "knowledge",
        "回家后先擦脚",
        {"world_ring": "nest", "importance": 0.8},
    )
    add_node(storage, "unclassified", "knowledge", "雨水会打湿毛发")

    # When
    projection = _memory_cognition_projection(elfie, spec)

    # Then
    assert projection["world_understanding"] == "世界仍在展开。"
    model = projection["world_model"]
    assert model["summary"] == "世界仍在展开。"
    assert [(ring["kind"], ring["label"]) for ring in model["rings"]] == [
        ("self", "自我"),
        ("family", "家人"),
        ("nest", "巢穴"),
        ("society", "社会"),
        ("outside", "外部世界"),
    ]
    assert model["rings"][2]["nodes"] == [
        {
            "id": "home_rule",
            "label": "回家后先擦脚",
            "kind": "knowledge",
            "weight": 0.8,
        }
    ]
    assert sum(len(ring["nodes"]) for ring in model["rings"]) == 1
