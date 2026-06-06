"""编码引擎单元测试

测试 MemoryEncoder 的核心编码流程：
- 高/低情绪强度事件的编码决策
- 刺激源触发编码
- episodic 节点创建和 metadata
- 三种边（involves、temporal、emotional）的构建
- 无前驱节点的边界情况
"""

from datetime import datetime, timedelta

import pytest

from elfie.brain.memory.encoding import MemoryEncoder
from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.node_types import (
    EdgeTypes,
    MemoryNode,
    NodeTypes,
)
from elfie.brain.memory.sensory_buffer import SensoryBuffer


class TestMemoryEncoder:
    """测试编码引擎核心功能"""

    @pytest.fixture
    def storage(self):
        """使用 :memory: 模式的 SQLite 存储"""
        gs = GraphStorage(db_path=":memory:")
        yield gs
        gs.close()

    @pytest.fixture
    def sensory_buffer(self):
        """容量 100 的感知缓冲"""
        return SensoryBuffer(max_size=100, window_seconds=3600)

    @pytest.fixture
    def encoder(self, storage, sensory_buffer):
        """MemoryEncoder 实例"""
        return MemoryEncoder(storage=storage, sensory_buffer=sensory_buffer)

    def test_encode_high_emotion(self, encoder, storage):
        """高情绪强度事件创建episodic节点并返回node_id"""
        node_id = encoder.encode(
            event_content="看到一只美丽的凤凰飞过天际",
            emotion="惊叹",
            intensity=85.0,
        )

        # 应返回非空节点ID
        assert node_id, "高情绪事件应返回节点ID"
        assert node_id.startswith("episodic_")

        # 节点应存在于存储中
        node = storage.get_node(node_id)
        assert node is not None
        assert node.type == NodeTypes.EPISODIC.value
        assert node.content == "看到一只美丽的凤凰飞过天际"

        # 缓冲中也应有记录
        assert len(encoder.sensory_buffer) == 1

    def test_encode_low_emotion(self, encoder, storage):
        """低情绪强度事件只进缓冲区，不创建episodic节点"""
        node_id = encoder.encode(
            event_content="看到一片普通的树叶飘落",
            emotion="平静",
            intensity=15.0,
        )

        # 应返回空字符串
        assert node_id == ""

        # 存储中应无节点
        assert storage.count_nodes(NodeTypes.EPISODIC.value) == 0

        # 缓冲中应有记录
        assert len(encoder.sensory_buffer) == 1

    def test_encode_with_stimulus(self, encoder, storage):
        """有stimulus的事件即使强度低也创建节点"""
        node_id = encoder.encode(
            event_content="听到远处传来低沉的吼声",
            emotion="警觉",
            intensity=20.0,
            stimulus="听觉",
        )

        # 有刺激源 → 应创建节点
        assert node_id, "有刺激源的事件应返回节点ID"
        assert node_id.startswith("episodic_")

        # 验证节点存在
        node = storage.get_node(node_id)
        assert node is not None
        assert node.metadata.get("stimulus") == "听觉"

    def test_create_episodic_node(self, encoder, storage):
        """创建episodic节点，验证metadata全部字段"""
        node_id = encoder.create_episodic_node(
            content="与老朋友偶遇",
            emotion="开心",
            intensity=75.0,
            stimulus="视觉",
            sensory={"visual": "熟悉的面孔"},
        )

        assert node_id.startswith("episodic_")

        node = storage.get_node(node_id)
        assert node is not None
        assert node.type == NodeTypes.EPISODIC.value

        # 验证 metadata 字段完整性
        meta = node.metadata
        assert meta["emotion"] == "开心"
        assert meta["emotion_intensity"] == 75.0
        assert meta["stimulus"] == "视觉"
        assert meta["importance"] == 0.75  # 75/100
        assert meta["recall_count"] == 0
        assert meta["consolidated"] is False
        assert "timestamp" in meta

        # 验证时间戳格式
        timestamp = datetime.fromisoformat(meta["timestamp"])
        assert isinstance(timestamp, datetime)

    def test_build_encoding_edges_involves(self, encoder, storage):
        """involves边：episodic→entity, weight=0.9"""
        # 先创建episodic节点
        node_id = encoder.create_episodic_node(
            content="看到一只猫爬上树", emotion="好奇", intensity=50.0
        )

        # 创建两个entity节点
        entity1_id = "entity_cat"
        entity2_id = "entity_tree"
        storage.add_node(
            MemoryNode(id=entity1_id, type=NodeTypes.ENTITY.value, content="猫")
        )
        storage.add_node(
            MemoryNode(id=entity2_id, type=NodeTypes.ENTITY.value, content="树")
        )

        # 构建involves边
        encoder.build_encoding_edges(
            node_id=node_id, entities=[entity1_id, entity2_id]
        )

        # 验证边
        edges = storage.get_edges(node_id, direction="outgoing")
        involves_edges = [e for e in edges if e.rel == EdgeTypes.INVOLVES.value]

        assert len(involves_edges) == 2
        targets = {e.target for e in involves_edges}
        assert entity1_id in targets
        assert entity2_id in targets

        # 验证权重
        for e in involves_edges:
            assert e.weight == 0.9

    def test_build_encoding_edges_temporal(self, encoder, storage):
        """temporal边权重按时间间隔计算"""
        # 手动创建前一个episodic节点（用 mock 控制时间戳）
        old_timestamp = (datetime.now() - timedelta(minutes=10)).isoformat()
        prev_id = "episodic_prev_001"
        storage.add_node(
            MemoryNode(
                id=prev_id,
                type=NodeTypes.EPISODIC.value,
                content="之前的事件",
                metadata={
                    "emotion": "平静",
                    "emotion_intensity": 30.0,
                    "timestamp": old_timestamp,
                },
                created_at=(datetime.now() - timedelta(minutes=10)).isoformat(),
            )
        )

        # 创建当前节点
        current_id = encoder.create_episodic_node(
            content="当前事件", emotion="平静", intensity=40.0
        )

        # 构建边（传入前驱节点ID）
        encoder.build_encoding_edges(
            node_id=current_id, prev_node_id=prev_id
        )

        # 验证 temporal 边（10分钟 → <30min → weight=0.7）
        edges = storage.get_edges(prev_id, direction="outgoing")
        temporal_edges = [e for e in edges if e.rel == EdgeTypes.TEMPORAL.value]
        assert len(temporal_edges) == 1
        assert temporal_edges[0].target == current_id
        assert temporal_edges[0].weight == 0.7

    def test_build_encoding_edges_temporal_weight_ranges(self, encoder, storage):
        """temporal边在不同时间范围的权重"""
        test_cases = [
            (timedelta(minutes=2), 0.9),   # <5min
            (timedelta(minutes=15), 0.7),  # <30min
            (timedelta(hours=1), 0.5),     # <2h
            (timedelta(hours=3), 0.3),     # >2h
        ]

        for offset, expected_weight in test_cases:
            # 用 mock 创建测试场景，每次使用不同的节点
            prev_ts = (datetime.now() - offset).isoformat()
            prev_id = f"episodic_prev_{offset.total_seconds()}_test"

            # 清理前一个相同ID的可能
            existing = storage.get_node(prev_id)
            if existing:
                # 如果已存在，跳过这个case或更新
                pass

            storage.add_node(
                MemoryNode(
                    id=prev_id,
                    type=NodeTypes.EPISODIC.value,
                    content=f"旧事件({offset})",
                    metadata={
                        "emotion": "平静",
                        "timestamp": prev_ts,
                    },
                    created_at=(datetime.now() - offset).isoformat(),
                )
            )

            current_id = f"episodic_current_{offset.total_seconds()}_test"
            storage.add_node(
                MemoryNode(
                    id=current_id,
                    type=NodeTypes.EPISODIC.value,
                    content=f"当前事件({offset})",
                    metadata={
                        "emotion": "平静",
                        "timestamp": datetime.now().isoformat(),
                    },
                    created_at=datetime.now().isoformat(),
                )
            )

            encoder.build_encoding_edges(
                node_id=current_id, prev_node_id=prev_id
            )

            edges = storage.get_edges(prev_id, direction="outgoing")
            temporal_edges = [e for e in edges if e.rel == EdgeTypes.TEMPORAL.value]
            matching = [e for e in temporal_edges if e.target == current_id]
            assert len(matching) == 1, f"offset={offset} 应有1条temporal边"
            assert matching[0].weight == expected_weight, (
                f"offset={offset}: 期望{expected_weight}, 实际{matching[0].weight}"
            )

    def test_build_encoding_edges_emotional(self, encoder, storage):
        """emotional边：与最近同情绪episodic连接"""
        # 先创建一个"开心"的旧节点
        old_happy_id = encoder.create_episodic_node(
            content="收到礼物很开心", emotion="开心", intensity=70.0
        )

        # 再创建一个"悲伤"的节点（不应匹配）
        encoder.create_episodic_node(
            content="打碎了花瓶", emotion="悲伤", intensity=60.0
        )

        # 创建新的"开心"事件
        new_happy_id = encoder.create_episodic_node(
            content="听到喜欢的音乐", emotion="开心", intensity=65.0
        )

        # 构建边（传入 emotion）
        encoder.build_encoding_edges(
            node_id=new_happy_id, emotion="开心"
        )

        # 验证 emotional 边存在：旧开心 → 新开心
        edges = storage.get_edges(old_happy_id, direction="outgoing")
        emotional_edges = [
            e for e in edges if e.rel == EdgeTypes.EMOTIONAL.value
        ]

        assert len(emotional_edges) == 1
        assert emotional_edges[0].target == new_happy_id
        assert emotional_edges[0].weight == 0.6

    def test_encode_no_previous_episodic(self, encoder, storage):
        """无前驱节点时不建temporal边"""
        # 第一次编码（数据库为空，无前驱）
        node_id = encoder.encode(
            event_content="第一次感知到光明",
            emotion="惊奇",
            intensity=90.0,
        )

        assert node_id, "首次编码应创建节点"

        # 验证所有边中无 temporal 类型
        edges = storage.get_edges(node_id, direction="incoming")
        temporal_incoming = [e for e in edges if e.rel == EdgeTypes.TEMPORAL.value]
        assert len(temporal_incoming) == 0

        edges = storage.get_edges(node_id, direction="outgoing")
        temporal_outgoing = [e for e in edges if e.rel == EdgeTypes.TEMPORAL.value]
        assert len(temporal_outgoing) == 0

    def test_encode_sensory_buffer_always_written(self, encoder, storage):
        """无论是否创建节点，感知事件始终写入缓冲区"""
        # 高强度事件
        encoder.encode(
            event_content="看到流星划过",
            emotion="震撼",
            intensity=95.0,
        )
        assert len(encoder.sensory_buffer) == 1

        # 低强度事件
        encoder.encode(
            event_content="微风吹过",
            emotion="平静",
            intensity=10.0,
        )
        assert len(encoder.sensory_buffer) == 2

    def test_get_similar_emotion_episodic_no_match(self, encoder, storage):
        """当没有同情绪节点时，get_similar_emotion_episodic返回None"""
        # 创建一些不同情绪的事件
        encoder.create_episodic_node(
            content="开心的事", emotion="开心", intensity=50.0
        )
        encoder.create_episodic_node(
            content="悲伤的事", emotion="悲伤", intensity=50.0
        )

        # 查询不存在的情绪
        result = encoder.get_similar_emotion_episodic("愤怒")
        assert result is None

    def test_get_previous_episodic_empty(self, encoder, storage):
        """数据库为空时返回None"""
        result = encoder.get_previous_episodic()
        assert result is None
