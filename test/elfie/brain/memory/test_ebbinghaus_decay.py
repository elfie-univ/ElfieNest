"""Ebbinghaus衰减遗忘计算单元测试"""

import math
from datetime import datetime, timedelta

from elfie.brain.memory.ebbinghaus_decay import EbbinghausDecay
from elfie.brain.memory.node_types import MemoryNode, NodeTypes


class TestEbbinghausDecay:
    """测试Ebbinghaus衰减遗忘计算"""

    EPOCH = "2026-01-01T00:00:00"

    def make_node(self, node_type: str, **metadata_kwargs) -> MemoryNode:
        """辅助方法：创建测试用记忆节点"""
        metadata = {
            "importance": 1.0,
            "recall_count": 0,
            "emotion_intensity": 0.0,
            **metadata_kwargs,
        }
        return MemoryNode(
            id="test_1",
            type=node_type,
            content="测试记忆",
            created_at=self.EPOCH,
            metadata=metadata,
        )

    def test_compute_strength_episodic(self):
        """情景记忆衰减：7天后半衰，强度约0.5（无回忆）"""
        decay = EbbinghausDecay()
        node = self.make_node(NodeTypes.EPISODIC.value)
        # 7天后（一个半衰期）
        t = (datetime.fromisoformat(self.EPOCH) + timedelta(days=7)).isoformat()
        strength = decay.compute_strength(node, t)
        # strength = 1.0 × e^(-ln(2) × 7 / 7 × 1) = 0.5
        assert abs(strength - 0.5) < 0.001, f"预期0.5，实际{strength}"

    def test_compute_strength_entity(self):
        """实体记忆衰减慢：7天后几乎不衰减"""
        decay = EbbinghausDecay()
        node = self.make_node(NodeTypes.ENTITY.value)
        t = (datetime.fromisoformat(self.EPOCH) + timedelta(days=7)).isoformat()
        strength = decay.compute_strength(node, t)
        # 实体半衰期365天，7天后几乎无衰减
        expected = math.exp(-math.log(2) * 7 / 365)
        assert abs(strength - expected) < 0.001, f"预期{expected:.4f}，实际{strength}"
        assert strength > 0.98, f"实体记忆衰减过快：{strength}"

    def test_compute_strength_knowledge(self):
        """知识记忆衰减：30天后半衰，强度约0.5"""
        decay = EbbinghausDecay()
        node = self.make_node(NodeTypes.KNOWLEDGE.value)
        t = (datetime.fromisoformat(self.EPOCH) + timedelta(days=30)).isoformat()
        strength = decay.compute_strength(node, t)
        # strength = 1.0 × e^(-ln(2) × 30 / 30 × 1) = 0.5
        assert abs(strength - 0.5) < 0.001, f"预期0.5，实际{strength}"

    def test_ghost_floor(self):
        """鬼影底线：强度永远不低于0.05"""
        decay = EbbinghausDecay()
        node = self.make_node(NodeTypes.EPISODIC.value)
        # 1000天后，强度应远低于0.05，被鬼影底线托住
        t = (datetime.fromisoformat(self.EPOCH) + timedelta(days=1000)).isoformat()
        strength = decay.compute_strength(node, t)
        assert strength == 0.05, f"鬼影底线失效，实际{strength}"

        # 更长时间也应保持0.05
        t2 = (datetime.fromisoformat(self.EPOCH) + timedelta(days=10000)).isoformat()
        strength2 = decay.compute_strength(node, t2)
        assert strength2 == 0.05, f"长时间后鬼影底线失效，实际{strength2}"

    def test_high_emotion_boost(self):
        """高情绪记忆：intensity > 0.7 → 半衰期×1.5 → 衰减更慢"""
        decay = EbbinghausDecay()
        node_normal = self.make_node(NodeTypes.EPISODIC.value, emotion_intensity=0.0)
        node_emotional = self.make_node(NodeTypes.EPISODIC.value, emotion_intensity=0.8)
        t = (datetime.fromisoformat(self.EPOCH) + timedelta(days=7)).isoformat()
        s_normal = decay.compute_strength(node_normal, t)
        s_emotional = decay.compute_strength(node_emotional, t)
        # 情绪记忆强度应明显高于普通记忆
        assert s_emotional > s_normal, (
            f"情绪记忆({s_emotional})应强于普通记忆({s_normal})"
        )
        # 半衰期×1.5 = 10.5天，7天后强度约为 e^(-ln2 × 7 / 10.5) ≈ 0.630
        expected = math.exp(-math.log(2) * 7 / (7 * 1.5))
        assert abs(s_emotional - expected) < 0.001, (
            f"预期{expected:.4f}，实际{s_emotional}"
        )

    def test_recall_count_stability(self):
        """回忆次数增加稳定性：recall_count越高，衰减越慢"""
        decay = EbbinghausDecay()
        node_no_recall = self.make_node(NodeTypes.EPISODIC.value, recall_count=0)
        node_recalled = self.make_node(NodeTypes.EPISODIC.value, recall_count=5)
        t = (datetime.fromisoformat(self.EPOCH) + timedelta(days=14)).isoformat()
        s_no_recall = decay.compute_strength(node_no_recall, t)
        s_recalled = decay.compute_strength(node_recalled, t)
        # 有回忆的记忆强度应更高
        assert s_recalled > s_no_recall, (
            f"回忆5次记忆({s_recalled})应强于无回忆({s_no_recall})"
        )
        # recall_count=5 → stability = 2.0
        # strength = e^(-ln2 × 14 / 7 × 2.0) = e^(-ln2) = 0.5
        expected = math.exp(-math.log(2) * 14 / (7 * 2.0))
        assert abs(s_recalled - expected) < 0.001, (
            f"预期{expected:.4f}，实际{s_recalled}"
        )

    def test_compute_decay(self):
        """衰减比例计算：0=无衰减，1=完全衰减"""
        decay = EbbinghausDecay()
        node = self.make_node(NodeTypes.EPISODIC.value)
        # 刚创建时衰减为0
        decay_0 = decay.compute_decay(node, self.EPOCH)
        assert abs(decay_0 - 0.0) < 0.001, f"刚创建时衰减应为0，实际{decay_0}"

        # 1000天后完全衰减（但受鬼影底线影响，不会完全到1）
        t = (datetime.fromisoformat(self.EPOCH) + timedelta(days=1000)).isoformat()
        decay_t = decay.compute_decay(node, t)
        # 鬼影底线：strength=0.05, importance=1.0 → decay=1-0.05=0.95
        assert abs(decay_t - 0.95) < 0.001, f"1000天后衰减应为0.95，实际{decay_t}"

    def test_get_half_life(self):
        """各类型半衰期获取"""
        decay = EbbinghausDecay()
        assert decay.get_half_life("episodic") == 7
        assert decay.get_half_life("entity") == 365
        assert decay.get_half_life("knowledge") == 30
        assert decay.get_half_life("pattern") == 60
        # 未知类型默认30天
        assert decay.get_half_life("unknown") == 30
        # 高情绪增强
        assert decay.get_half_life("episodic", 0.8) == 7 * 1.5
        # 低情绪不增强
        assert decay.get_half_life("episodic", 0.5) == 7
