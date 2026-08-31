"""5区域上下文组装单元测试

测试 MemoryRecallFormatter 的5个区域组装方法及完整上下文组装流程。
每个区域独立测试，最后测试完整的 assemble 入口。
"""

from unittest.mock import MagicMock

import pytest

from elfie.brain.memory.node_types import MemoryNode, RetrievalQuery
from elfie.brain.memory.recall_formatter import MemoryRecallFormatter


def _make_node(node_id: str, content: str, **meta) -> MemoryNode:
    """辅助构造测试用的 MemoryNode"""
    return MemoryNode(
        id=node_id,
        type="episodic",
        content=content,
        metadata={
            "timestamp": "2026-06-06T08:00:00",
            "_retrieval_score": 0.8,
            **meta,
        },
        created_at="2026-06-06T08:00:00",
    )


class TestMemoryRecallFormatter:
    """5区域上下文组装测试"""

    @pytest.fixture
    def assembler(self):
        """创建全部mock的 MemoryRecallFormatter 实例"""
        storage = MagicMock()
        retriever = MagicMock()
        spreading = MagicMock()
        decay = MagicMock()
        weighting = MagicMock()
        return MemoryRecallFormatter(
            storage=storage,
            retriever=retriever,
            spreading=spreading,
            decay=decay,
            weighting=weighting,
        )

    # ──────────── 区域1：实体 ────────────

    def test_assemble_entity_zone(self, assembler):
        """实体区域：列出关于实体的已知信息"""
        assembler.storage.get_nodes_by_type.return_value = [
            MemoryNode(id="ent_1", type="entity", content="主人"),
            MemoryNode(id="ent_2", type="entity", content="猫"),
        ]
        result = assembler._assemble_entity_zone(["主人"])
        assert "关于主人你知道什么：" in result
        assert "  - 主人" in result

    def test_assemble_entity_zone_unknown(self, assembler):
        """实体区域：未知实体显示'还不太了解'"""
        assembler.storage.get_nodes_by_type.return_value = []
        result = assembler._assemble_entity_zone(["火星人"])
        assert "关于火星人你知道什么：" in result
        assert "你对火星人还不太了解" in result

    def test_assemble_entity_zone_empty(self, assembler):
        """实体区域：无实体返回空字符串"""
        assembler.storage.get_nodes_by_type.return_value = []
        result = assembler._assemble_entity_zone([])
        assert result == ""

    # ──────────── 区域2：最近经历 ────────────

    def test_assemble_recent_zone(self, assembler):
        """最近经历区域：列出最近的记忆节点含记忆强度"""
        nodes = [
            _make_node("ep_1", "主人喂了我鱼味食物"),
            _make_node("ep_2", "主人摸了我的头"),
        ]
        assembler.decay.compute_strength.return_value = 0.8
        query = RetrievalQuery(current_time="2026-06-06T10:00:00")

        result = assembler._assemble_recent_zone(nodes, query)
        assert "最近相关经历：" in result
        assert "鱼味食物" in result
        assert "主人摸了我的头" in result
        # 含记忆强度（compute_strength返回0.8）
        assert "0.8" in result

    def test_assemble_recent_zone_empty(self, assembler):
        """最近经历区域：无节点返回空字符串"""
        query = RetrievalQuery()
        result = assembler._assemble_recent_zone([], query)
        assert result == ""

    # ──────────── 区域3：联想 ────────────

    def test_assemble_association_zone(self, assembler):
        """联想区域：扩散激活结果列出关联节点"""
        assembler.spreading.spread.return_value = {
            "assoc_1": 0.6,
            "assoc_2": 0.4,
        }
        assembler.storage.get_node.side_effect = [
            MemoryNode(id="assoc_1", type="entity", content="鱼味食物"),
            MemoryNode(id="assoc_2", type="episodic", content="厨房"),
        ]

        result = assembler._assemble_association_zone(["ep_1", "ep_2"])
        assert "联想到：" in result
        assert "鱼味食物" in result
        assert "厨房" in result

    def test_assemble_association_zone_empty_seeds(self, assembler):
        """联想区域：无种子ID返回空字符串"""
        result = assembler._assemble_association_zone([])
        assert result == ""

    def test_assemble_association_zone_empty_activation(self, assembler):
        """联想区域：扩散激活无结果返回空字符串"""
        assembler.spreading.spread.return_value = {}
        result = assembler._assemble_association_zone(["ep_1"])
        assert result == ""

    # ──────────── 区域4：预测 ────────────

    def test_assemble_prediction_zone(self, assembler):
        """预测区域：基于最近事件和实体推测"""
        result = assembler._assemble_prediction_zone(["现在8点主人走过来"], ["主人"])
        assert "预测灵感：" in result
        assert "主人走过来" in result
        assert "与主人相关的可能事件" in result

    def test_assemble_prediction_zone_only_events(self, assembler):
        """预测区域：只有事件，没有实体"""
        result = assembler._assemble_prediction_zone(["天快黑了"], [])
        assert "预测灵感：" in result
        assert "天快黑了" in result

    def test_assemble_prediction_zone_empty(self, assembler):
        """预测区域：无事件无实体返回空字符串"""
        result = assembler._assemble_prediction_zone([], [])
        assert result == ""

    # ──────────── 区域5：情绪 ────────────

    def test_assemble_emotion_zone(self, assembler):
        """情绪区域：当前情绪对记忆的影响"""
        assembler.weighting.get_weights.return_value = {
            "semantic": 0.40,
            "mood": 0.30,
            "recency": 0.15,
            "spread": 0.15,
        }

        result = assembler._assemble_emotion_zone("happy", 0.8)
        assert "当前情绪对你记忆的影响：" in result
        assert "开心" in result
        assert "强度0.8" in result
        assert "检索权重" in result
        assert "语义40%" in result
        assert "更容易想起愉快的事" in result

    def test_assemble_emotion_zone_negative_high(self, assembler):
        """情绪区域：负面情绪高强度时的提示"""
        assembler.weighting.get_weights.return_value = {
            "semantic": 0.25,
            "mood": 0.45,
            "recency": 0.10,
            "spread": 0.20,
        }

        result = assembler._assemble_emotion_zone("fear", 0.9)
        assert "害怕" in result
        assert "强度0.9" in result
        assert "更容易想起相似经历" in result

    def test_assemble_emotion_zone_low_intensity(self, assembler):
        """情绪区域：低强度时不显示情绪加强提示"""
        assembler.weighting.get_weights.return_value = {
            "semantic": 0.55,
            "mood": 0.15,
            "recency": 0.20,
            "spread": 0.10,
        }

        result = assembler._assemble_emotion_zone("calm", 0.3)
        assert "平静" in result
        assert "更容易" not in result  # 低强度不显示加强提示

    def test_assemble_emotion_zone_empty(self, assembler):
        """情绪区域：无情绪返回空字符串"""
        result = assembler._assemble_emotion_zone("", 0.0)
        assert result == ""

    # ──────────── 完整组装 ────────────

    def test_assemble_full_context(self, assembler):
        """完整5区域上下文组装"""
        # 配置所有mock返回值
        assembler.retriever.retrieve.return_value = [
            _make_node("ep_1", "主人喂了我鱼味食物"),
            _make_node("ep_2", "主人摸了我的头"),
        ]
        assembler.spreading.spread.return_value = {
            "assoc_1": 0.6,
        }
        assembler.storage.get_node.return_value = MemoryNode(
            id="assoc_1", type="entity", content="鱼味食物"
        )
        assembler.storage.get_nodes_by_type.return_value = [
            MemoryNode(id="ent_1", type="entity", content="主人"),
        ]
        assembler.decay.compute_strength.return_value = 0.8
        assembler.weighting.get_weights.return_value = {
            "semantic": 0.40,
            "mood": 0.30,
            "recency": 0.15,
            "spread": 0.15,
        }

        query = RetrievalQuery(
            current_emotion="happy",
            current_intensity=0.8,
            current_entities=["主人"],
            current_time="2026-06-06T10:00:00",
            recent_events=["现在8点主人走过来"],
        )

        result = assembler.assemble(query, top_k=10)

        # Selfhood is supplied by Brain's fixed header, not Memory recall.
        assert "核心认知" not in result

        # 应包含5个区域
        assert "关于主人你知道什么" in result
        assert "最近相关经历：" in result
        assert "联想到：" in result
        assert "预测灵感：" in result
        assert "当前情绪对你记忆的影响：" in result

        # 总字符数不超过2000（≈800 tokens）
        assert len(result) <= 2000, f"上下文过长: {len(result)}字符，超过了2000限制"

    def test_assemble_empty_query(self, assembler):
        """空查询：不伪造 Selfhood 文本"""
        assembler.retriever.retrieve.return_value = []

        query = RetrievalQuery()
        result = assembler.assemble(query, top_k=10)

        assert result == ""

    def test_assemble_with_ordinary_memory_only(self, assembler):
        """包含普通记忆和动态检索提示，但不包含 Selfhood"""
        assembler.retriever.retrieve.return_value = [
            _make_node("ep_1", "主人喂了我鱼味食物"),
        ]
        assembler.spreading.spread.return_value = {}
        assembler.storage.get_nodes_by_type.return_value = []
        assembler.decay.compute_strength.return_value = 0.8
        assembler.weighting.get_weights.return_value = {
            "semantic": 0.55,
            "mood": 0.15,
            "recency": 0.20,
            "spread": 0.10,
        }

        query = RetrievalQuery(
            current_emotion="calm",
            current_intensity=0.5,
            current_time="2026-06-06T10:00:00",
        )

        result = assembler.assemble(query, top_k=10)

        assert "核心认知" not in result
        # 情绪区域
        assert "当前情绪对你记忆的影响：" in result
        assert "平静" in result
        # 最近经历区域（有检索结果）
        assert "最近相关经历：" in result
        # 实体区域不应出现（无实体）
        assert "关于" not in result
