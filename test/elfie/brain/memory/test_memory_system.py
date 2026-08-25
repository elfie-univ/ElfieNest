"""MemorySystem 门面类测试

测试MemorySystem完整流程：
- 初始化所有组件
- 记录事件
- 检索记忆
- 运行巩固
- 获取核心认知
- 获取5区域上下文
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.memory import (
    EbbinghausDecay,
    EmotionWeighting,
    MemoryConsolidator,
    MemoryEncoder,
    MemoryRecallFormatter,
    MemoryRetriever,
    MemorySelfNarrativeProjection,
    MemorySystem,
    SensoryBuffer,
    SensoryIndexer,
    SpreadingActivation,
)
from elfie.message_types import EventId
from infrastructure.persistence.configuration.bundled_defaults import (
    load_selfhood_defaults,
)
from test.elfie.brain.memory.fake_store import FakeMemoryStore

_PERSONALITY_DATA = load_selfhood_defaults()


def _new_memory_system() -> MemorySystem:
    return MemorySystem(
        storage=FakeMemoryStore.in_memory(),
        personality_data=_PERSONALITY_DATA,
    )


class TestMemorySystem:
    """MemorySystem 门面类测试"""

    def test_memory_system_accepts_a_brain_owned_storage_port(self):
        store = FakeMemoryStore.in_memory()
        ms = MemorySystem(storage=store, personality_data=_PERSONALITY_DATA)

        assert ms.storage is store
        ms.close()
        assert store.count_nodes() >= 4
        store.close()

    def test_memory_system_init(self):
        """初始化所有组件"""
        ms = _new_memory_system()
        assert ms.storage is not None
        assert isinstance(ms.storage, FakeMemoryStore)
        assert ms.sensory_buffer is not None
        assert isinstance(ms.sensory_buffer, SensoryBuffer)
        assert ms.self_narrative is not None
        assert isinstance(ms.self_narrative, MemorySelfNarrativeProjection)
        assert ms.encoder is not None
        assert isinstance(ms.encoder, MemoryEncoder)
        assert ms.retriever is not None
        assert isinstance(ms.retriever, MemoryRetriever)
        assert ms.spreading is not None
        assert isinstance(ms.spreading, SpreadingActivation)
        assert ms.decay is not None
        assert isinstance(ms.decay, EbbinghausDecay)
        assert ms.weighting is not None
        assert isinstance(ms.weighting, EmotionWeighting)
        assert ms.consolidator is not None
        assert isinstance(ms.consolidator, MemoryConsolidator)
        assert ms.recall_formatter is not None
        assert isinstance(ms.recall_formatter, MemoryRecallFormatter)
        assert ms.sensory_indexer is not None
        assert isinstance(ms.sensory_indexer, SensoryIndexer)

    def test_record_episode_high_intensity(self):
        """记录高强度事件 -> 创建episodic节点"""
        ms = _new_memory_system()
        node_id = ms.record_episode(
            content="今天主人喂我吃了美味的鸡肉",
            emotion="happy",
            intensity=80.0,
        )
        assert node_id, "高强度事件应返回非空node_id"
        assert node_id.startswith("episodic_")

    def test_record_episode_low_intensity(self):
        """记录低强度事件 -> 仅写入缓冲，不创建节点"""
        ms = _new_memory_system()
        node_id = ms.record_episode(
            content="今天天气很好",
            emotion="calm",
            intensity=10.0,
        )
        assert node_id == "", "低强度无刺激源事件应返回空字符串"

    def test_record_episode_with_stimulus(self):
        """记录有刺激源的事件 -> 即使低强度也创建节点"""
        ms = _new_memory_system()
        node_id = ms.record_episode(
            content="听到主人的脚步声",
            emotion="happy",
            intensity=20.0,
            stimulus="听觉",
        )
        assert node_id, "有刺激源的事件应返回非空node_id"

    def test_record_episode_preserves_source_event_ids_on_the_node(self):
        ms = _new_memory_system()

        node_id = ms.record_episode(
            content="主人带我看到了 Elfaria 的星光",
            emotion="curious",
            intensity=80.0,
            source_event_ids=(EventId("owner-event-1"),),
        )

        assert ms.storage.get_node(node_id).metadata["source_event_ids"] == [
            "owner-event-1"
        ]

    def test_retrieve_memories(self):
        """检索记忆：记录事件后应能检索到"""
        ms = _new_memory_system()
        ms.record_episode(
            content="今天去花园散步了，看到很多花",
            emotion="happy",
            intensity=70.0,
        )
        ms.record_episode(
            content="主人给我做了美味的晚餐",
            emotion="happy",
            intensity=85.0,
        )

        results = ms.retrieve_relevant_memories("花园", top_k=5)
        assert len(results) >= 1
        found = any("花园" in r for r in results)
        assert found, f"检索结果应包含'花园'，实际结果: {results}"

    def test_retrieve_memories_empty(self):
        """检索空库应返回空列表"""
        ms = _new_memory_system()
        results = ms.retrieve_relevant_memories("任何内容", top_k=5)
        assert results == []

    def test_retrieve_memories_with_emotion(self):
        """检索时传入情绪参数"""
        ms = _new_memory_system()
        ms.record_episode(content="摔了一跤，好痛", emotion="sadness", intensity=80.0)
        ms.record_episode(content="主人表扬了我", emotion="happy", intensity=90.0)

        results = ms.retrieve_relevant_memories(
            "今天", top_k=5, current_emotion="sadness"
        )
        assert isinstance(results, list)

    def test_run_consolidation(self):
        """运行巩固流程（无LLM降级模式）"""
        ms = _new_memory_system()

        class MockRuntime:
            def ask_with_food(self, prompt, **kwargs):
                return "与主人在一起很开心\n食物让艾菲感到满足"

        ms.record_episode(content="主人喂我吃饭", emotion="happy", intensity=70.0)
        ms.record_episode(content="主人带我去散步", emotion="happy", intensity=65.0)
        ms.record_episode(content="主人抚摸我的头", emotion="happy", intensity=75.0)

        result = ms.run_consolidation(MockRuntime())
        assert isinstance(result, dict)
        assert "consolidated_count" in result
        assert "knowledge_created" in result
        assert "edges_created" in result

    def test_run_consolidation_empty(self):
        """无未巩固节点时巩固应跳过"""
        ms = _new_memory_system()
        result = ms.run_consolidation()
        assert isinstance(result, dict)
        assert result["consolidated_count"] == 0

    def test_get_self_narrative(self):
        """获取核心认知"""
        ms = _new_memory_system()
        core_text = ms.get_self_narrative()
        assert isinstance(core_text, dict)
        assert "identity" in core_text
        assert "relation" in core_text
        assert "world" in core_text
        assert "tendency" in core_text

    def test_recall_context(self):
        """获取5区域上下文文本"""
        ms = _new_memory_system()
        ms.record_episode(content="主人喂我吃了鸡肉", emotion="happy", intensity=80.0)
        ms.record_episode(content="今天去了公园", emotion="happy", intensity=60.0)

        context = ms.recall_context(
            query="主人",
            emotion="happy",
            intensity=0.8,
            entities=["主人"],
            current_time="2026-06-06T10:00:00",
        )
        assert isinstance(context, str)
        assert len(context) > 0
        assert "核心认知" in context

    def test_backward_compatible_record_episode(self):
        """兼容旧API关键字参数名"""
        ms = _new_memory_system()
        node_id = ms.record_episode(
            event_description="测试旧API参数名",
            emotion_tag="happy",
            emotion_intensity=80.0,
        )
        assert node_id, "使用旧API参数名应正常工作"

    def test_backward_compatible_retrieve(self):
        """兼容旧API调用方式（MemoryRecallFormatter使用方式）"""
        ms = _new_memory_system()
        ms.record_episode(content="和主人一起玩耍", emotion="happy", intensity=90.0)

        retrieved = ms.retrieve_relevant_memories("玩耍", current_emotion="happy")
        assert isinstance(retrieved, list)
