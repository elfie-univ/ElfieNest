"""数据模型单元测试

测试 MemoryNode、Edge、RetrievalQuery 数据类和 NodeTypes、EdgeTypes 枚举。
"""

import json
from datetime import datetime

import pytest

from elfie.brain.memory.node_types import (
    Edge,
    EdgeTypes,
    MemoryMetadata,
    MemoryNode,
    NodeTypes,
    RetrievalQuery,
)


class TestNodeTypes:
    """测试节点类型枚举"""

    def test_enum_values(self):
        """验证 NodeTypes 枚举值正确"""
        assert NodeTypes.EPISODIC.value == "episodic"
        assert NodeTypes.ENTITY.value == "entity"
        assert NodeTypes.KNOWLEDGE.value == "knowledge"
        assert NodeTypes.PATTERN.value == "pattern"

    def test_enum_members_count(self):
        """验证 NodeTypes 包含 4 个成员"""
        assert len(NodeTypes) == 4

    def test_enum_via_string(self):
        """验证可以通过字符串值构造枚举"""
        assert NodeTypes("episodic") == NodeTypes.EPISODIC
        assert NodeTypes("entity") == NodeTypes.ENTITY
        assert NodeTypes("knowledge") == NodeTypes.KNOWLEDGE
        assert NodeTypes("pattern") == NodeTypes.PATTERN


class TestEdgeTypes:
    """测试边类型枚举"""

    def test_enum_values(self):
        """验证 EdgeTypes 枚举值正确"""
        assert EdgeTypes.INVOLVES.value == "involves"
        assert EdgeTypes.TEMPORAL.value == "temporal"
        assert EdgeTypes.EMOTIONAL.value == "emotional"
        assert EdgeTypes.CAUSAL.value == "causal"
        assert EdgeTypes.SUPPORTS.value == "supports"
        assert EdgeTypes.ABOUT.value == "about"
        assert EdgeTypes.IMPLIES.value == "implies"

    def test_enum_members_count(self):
        """验证 EdgeTypes 包含 7 个成员"""
        assert len(EdgeTypes) == 7


class TestEdge:
    """测试边数据类"""

    def test_default_weight(self):
        """验证 weight 默认值为 0.5"""
        edge = Edge(target="node_2", rel="involves")
        assert edge.target == "node_2"
        assert edge.rel == "involves"
        assert edge.weight == 0.5

    def test_custom_weight(self):
        """验证可以自定义 weight"""
        edge = Edge(target="node_2", rel="temporal", weight=0.9)
        assert edge.weight == 0.9

    def test_edge_types_as_rel(self):
        """验证可以使用枚举值作为 rel 字符串"""
        edge = Edge(target="node_3", rel=EdgeTypes.CAUSAL.value)
        assert edge.rel == "causal"

    def test_edge_is_dataclass(self):
        """验证 Edge 是 dataclass（有 __dataclass_fields__）"""
        import dataclasses

        assert dataclasses.is_dataclass(Edge)


class TestMemoryNode:
    """测试记忆节点数据类"""

    def test_minimal_creation(self):
        """验证最少参数创建节点"""
        node = MemoryNode(id="n1", type="episodic", content="今天遇到了朋友")
        assert node.id == "n1"
        assert node.type == "episodic"
        assert node.content == "今天遇到了朋友"
        assert node.metadata == {}
        assert node.edges == []
        assert node.created_at is None
        assert node.updated_at is None

    def test_full_creation(self):
        """验证完整参数创建节点"""
        edges = [
            Edge(target="n2", rel="involves", weight=0.8),
            Edge(target="n3", rel="temporal", weight=0.6),
        ]
        now = datetime.now().isoformat()
        node = MemoryNode(
            id="n1",
            type="episodic",
            content="今天遇到了朋友",
            metadata={"emotion": "happy", "location": "park"},
            edges=edges,
            created_at=now,
            updated_at=now,
        )
        assert node.id == "n1"
        assert node.metadata["emotion"] == "happy"
        assert len(node.edges) == 2
        assert node.created_at == now
        assert node.updated_at == now

    def test_with_node_types_enum(self):
        """验证可以使用 NodeTypes 枚举值设置 type"""
        node = MemoryNode(
            id="n2", type=NodeTypes.KNOWLEDGE.value, content="猫是哺乳动物"
        )
        assert node.type == "knowledge"

    def test_metadata_mutable_defaults(self):
        """验证每个实例的 metadata 和 edges 相互独立"""
        node1 = MemoryNode(id="a", type="entity", content="猫")
        node2 = MemoryNode(id="b", type="entity", content="狗")
        node1.metadata["color"] = "black"
        assert "color" not in node2.metadata

    def test_serialize_metadata_to_json(self):
        """验证 metadata 可序列化为 JSON"""
        node = MemoryNode(
            id="n1",
            type="episodic",
            content="test",
            metadata={"score": 42, "tags": ["a", "b"]},
        )
        dumped = json.dumps(node.metadata)
        loaded = json.loads(dumped)
        assert loaded["score"] == 42
        assert loaded["tags"] == ["a", "b"]

    def test_metadata_rejects_non_json_values_on_construction_and_update(self):
        with pytest.raises(TypeError):
            MemoryMetadata({"bad": object()})

        metadata = MemoryMetadata()
        with pytest.raises(TypeError):
            metadata.update({"bad": object()})

    def test_memory_node_is_dataclass(self):
        """验证 MemoryNode 是 dataclass"""
        import dataclasses

        assert dataclasses.is_dataclass(MemoryNode)


class TestRetrievalQuery:
    """测试检索查询数据类"""

    def test_default_creation(self):
        """验证默认参数创建查询"""
        query = RetrievalQuery()
        assert query.text_query == ""
        assert query.current_emotion == ""
        assert query.current_intensity == 0.0
        assert query.current_entities == []
        assert query.current_time == ""
        assert query.current_sensory == {}
        assert query.recent_events == []

    def test_full_creation(self):
        """验证完整参数创建查询"""
        query = RetrievalQuery(
            text_query="今天发生了什么？",
            current_emotion="happy",
            current_intensity=0.8,
            current_entities=["朋友", "公园"],
            current_time="2026-06-06 10:00:00",
            current_sensory={"visual": "阳光明媚", "auditory": "鸟鸣"},
            recent_events=["晨跑", "吃早餐"],
        )
        assert query.text_query == "今天发生了什么？"
        assert query.current_emotion == "happy"
        assert query.current_intensity == 0.8
        assert len(query.current_entities) == 2
        assert query.current_sensory["visual"] == "阳光明媚"
        assert len(query.recent_events) == 2

    def test_retrieval_query_is_dataclass(self):
        """验证 RetrievalQuery 是 dataclass"""
        import dataclasses

        assert dataclasses.is_dataclass(RetrievalQuery)
