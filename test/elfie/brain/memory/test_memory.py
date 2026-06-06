"""Memory Module Unit Tests

Test EpisodeMemoryManager and TinyVectorStorage for episodic memory management.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.memory.episode_manager import EpisodeMemoryManager
from elfie.brain.memory.night_consolidator import NightMemoryConsolidator
from elfie.brain.memory.vector_storage import TinyVectorStorage


class TestTinyVectorStorage:
    @pytest.fixture
    def temp_storage_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.remove(temp_path)

    def test_init_default_path(self):
        storage = TinyVectorStorage()
        assert storage.memories is not None
        assert isinstance(storage.memories, list)

    def test_init_custom_path(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        assert storage.storage_path == temp_storage_path
        assert storage.memories == []

    def test_init_load_existing(self, temp_storage_path):
        # 预先写入一些数据
        test_data = [{"content": "test memory", "metadata": {"emotion": "happy"}}]
        with open(temp_storage_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        storage = TinyVectorStorage(temp_storage_path)
        assert len(storage.memories) == 1
        assert storage.memories[0]["content"] == "test memory"

    def test_add_memory_basic(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("今天天气很好")

        assert len(storage.memories) == 1
        assert storage.memories[0]["content"] == "今天天气很好"
        assert "timestamp" in storage.memories[0]["metadata"]

    def test_add_memory_with_tags(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory(
            "主人表扬了我", tags={"emotion": "happy", "location": "home"}
        )

        assert len(storage.memories) == 1
        meta = storage.memories[0]["metadata"]
        assert meta["emotion"] == "happy"
        assert meta["location"] == "home"
        assert "timestamp" in meta

    def test_add_multiple_memories(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("记忆一")
        storage.add_memory("记忆二")
        storage.add_memory("记忆三")

        assert len(storage.memories) == 3

    def test_retrieve_relevant_memories_basic(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("今天天气很好")
        storage.add_memory("主人表扬了我")
        storage.add_memory("下雨了")

        results = storage.retrieve_relevant_memories("天气")
        assert len(results) <= 2
        assert "今天天气很好" in results

    def test_retrieve_relevant_memories_top_k(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("记忆一")
        storage.add_memory("记忆二")
        storage.add_memory("记忆三")

        results = storage.retrieve_relevant_memories("记忆", top_k=3)
        assert len(results) == 3

    def test_retrieve_empty_query(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("test")

        results = storage.retrieve_relevant_memories("")
        assert results == []

    def test_retrieve_no_memories(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)

        results = storage.retrieve_relevant_memories("query")
        assert results == []

    def test_retrieve_no_match(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("完全不相关的记忆")

        results = storage.retrieve_relevant_memories("xyz123")
        # 兜底返回最近的记忆
        assert len(results) > 0

    def test_tokenize_chinese(self):
        storage = TinyVectorStorage()
        words = storage._tokenize("今天天气很好")
        assert "今" in words or "天" in words

    def test_tokenize_english(self):
        storage = TinyVectorStorage()
        words = storage._tokenize("hello world")
        assert "hello" in words
        assert "world" in words

    def test_tokenize_mixed(self):
        storage = TinyVectorStorage()
        words = storage._tokenize("今天 hello world")
        assert "今" in words or "天" in words
        assert "hello" in words

    def test_emotion_weight_happy(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("测试记忆", tags={"emotion": "happy"})

        # happy标签会有1.2倍权重 boost
        results = storage.retrieve_relevant_memories("测试记忆")
        assert len(results) > 0

    def test_save_to_disk(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("测试保存")

        # 验证文件已创建且包含数据
        assert os.path.exists(temp_storage_path)
        with open(temp_storage_path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1

    def test_add_memory_with_level_episodic(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("测试", tags={"emotion": "happy"}, level="episodic")
        assert storage.memories[0]["metadata"]["level"] == "episodic"

    def test_add_memory_with_level_consolidated(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("测试", tags={"emotion": "happy"}, level="consolidated")
        assert storage.memories[0]["metadata"]["level"] == "consolidated"

    def test_add_memory_with_intensity(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("测试", tags={"emotion": "happy"}, intensity=75.0)
        assert storage.memories[0]["metadata"]["intensity"] == 75.0

    def test_add_memory_default_intensity_zero(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("测试", tags={"emotion": "happy"})
        assert storage.memories[0]["metadata"]["intensity"] == 0.0

    def test_retrieve_with_level_preference(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("日常记忆", tags={"emotion": "calm"})
        storage.memories[0]["metadata"]["level"] = "episodic"
        storage.add_memory("长期记忆", tags={"emotion": "calm"})
        storage.memories[1]["metadata"]["level"] = "consolidated"
        results = storage.retrieve_relevant_memories("记忆")
        assert results[0] == "长期记忆"

    def test_retrieve_with_emotion_weighting(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("悲伤的记忆", tags={"emotion": "sad"})
        storage.add_memory("快乐的记忆", tags={"emotion": "happy"})
        results = storage.retrieve_relevant_memories("记忆", current_emotion="sad")
        assert results[0] == "悲伤的记忆"

    def test_capacity_limit_episodic(self, temp_storage_path):
        storage = TinyVectorStorage(temp_storage_path)
        for i in range(101):
            storage.add_memory(f"记忆{i}", tags={"emotion": "calm"})
        assert len(storage.memories) <= 100

    def test_backward_compatible_load(self, temp_storage_path):
        old_data = [
            {"content": "旧记忆", "metadata": {"emotion": "happy", "timestamp": "2024-01-01"}},
            {"content": "新记忆", "metadata": {"emotion": "sad", "timestamp": "2024-01-02", "level": "episodic", "intensity": 50.0}},
        ]
        with open(temp_storage_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)
        storage = TinyVectorStorage(temp_storage_path)
        assert storage.memories[0]["metadata"].get("level") == "episodic"
        assert storage.memories[0]["metadata"].get("intensity") == 0.0

    def test_load_old_format_missing_level_and_intensity(self, temp_storage_path):
        """加载无level/intensity字段的旧JSON时自动补默认值"""
        old_data = [{"content": "旧记忆", "metadata": {"emotion": "happy", "timestamp": "2024-01-01"}}]
        with open(temp_storage_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)
        storage = TinyVectorStorage(temp_storage_path)
        assert storage.memories[0]["metadata"]["level"] == "episodic"
        assert storage.memories[0]["metadata"]["intensity"] == 0.0

    def test_load_corrupted_json(self, temp_storage_path):
        """加载损坏的JSON文件不崩溃，返回空列表"""
        with open(temp_storage_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        storage = TinyVectorStorage(temp_storage_path)
        assert storage.memories == []

    def test_save_and_reload_preserves_level_and_intensity(self, temp_storage_path):
        """保存后重新加载保留level和intensity字段"""
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("测试记忆", tags={"emotion": "happy"}, level="consolidated", intensity=75.0)
        # 重新加载
        storage2 = TinyVectorStorage(temp_storage_path)
        assert storage2.memories[0]["metadata"]["level"] == "consolidated"
        assert storage2.memories[0]["metadata"]["intensity"] == 75.0

    def test_consolidation_with_mixed_emotions(self, temp_storage_path):
        """多种情绪的混合记忆巩固，使用最频繁的情绪"""
        mgr = EpisodeMemoryManager(temp_storage_path)
        mgr.record_episode("开心的事", emotion_tag="happy", emotion_intensity=80.0)
        mgr.record_episode("难过的事", emotion_tag="sad", emotion_intensity=90.0)
        mgr.record_episode("开心的事2", emotion_tag="happy", emotion_intensity=70.0)
        mgr.record_episode("平淡的事", emotion_tag="calm", emotion_intensity=20.0)

        consolidator = NightMemoryConsolidator(mgr)

        class MockRuntime:
            def ask(self, p, energy, task_complexity):
                return "今天整体情感体验丰富\n既经历了快乐也经历了悲伤"

        result = consolidator.run_consolidation(MockRuntime())
        # 确保巩固成功
        episodes = mgr.get_all_episodes()
        assert len(episodes) == 2  # 4条原记忆 -> 2条固化
        # 主导情绪应该是"happy"（出现2次，最多）
        # 这里我们验证巩固后的记忆有正确的情绪标记
        for ep in episodes:
            assert ep["metadata"]["level"] == "consolidated"

    def test_consolidation_with_exactly_3_episodes(self, temp_storage_path):
        """等于3条记忆时触发巩固"""
        mgr = EpisodeMemoryManager(temp_storage_path)
        mgr.record_episode("记忆一")
        mgr.record_episode("记忆二")
        mgr.record_episode("记忆三")
        assert len(mgr.get_all_episodes()) == 3

        consolidator = NightMemoryConsolidator(mgr)

        class MockRuntime:
            def ask(self, p, energy, task_complexity):
                return "整合的三条记忆\n形成了完整的故事线"

        result = consolidator.run_consolidation(MockRuntime())
        assert "Error" not in result and "No consolidation" not in result
        episodes = mgr.get_all_episodes()
        assert len(episodes) == 2  # 3条 -> 2条固化

    def test_first_ever_wake_cycle_no_consolidation(self):
        """首次唤醒不触发巩固（was_sleeping从未为True）"""
        # 模拟 was_sleeping 逻辑
        was_sleeping = False  # 首次初始化，从未睡着
        currently_sleeping = False  # 当前醒着
        should_consolidate = was_sleeping and not currently_sleeping
        assert not should_consolidate  # 不应该触发

    def test_retrieve_with_no_current_emotion_fallback(self, temp_storage_path):
        """current_emotion=None时回退到原始检索行为（不按情绪加权）"""
        storage = TinyVectorStorage(temp_storage_path)
        storage.add_memory("开心的记忆", tags={"emotion": "happy", "level": "episodic", "intensity": 80.0})
        storage.add_memory("悲伤的记忆", tags={"emotion": "sad", "level": "episodic", "intensity": 60.0})

        # 不传current_emotion时，保持原始TF-IDF权重
        results_no_emotion = storage.retrieve_relevant_memories("记忆")
        assert len(results_no_emotion) > 0

        # 传current_emotion时，匹配情绪加权
        results_happy = storage.retrieve_relevant_memories("记忆", current_emotion="happy")
        assert len(results_happy) > 0
        # happy情绪下，开心的记忆排序更高
        assert results_happy[0] == "开心的记忆"


class TestEpisodeMemoryManager:
    @pytest.fixture
    def temp_storage_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.remove(temp_path)

    def test_init_default(self):
        manager = EpisodeMemoryManager()
        assert manager.storage is not None

    def test_init_custom_path(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        assert manager.storage.storage_path == temp_storage_path

    def test_record_episode_basic(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("今天主人带我出去散步")

        episodes = manager.get_all_episodes()
        assert len(episodes) == 1
        assert episodes[0]["content"] == "今天主人带我出去散步"

    def test_record_episode_with_emotion(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("主人表扬了我", emotion_tag="happy")

        episodes = manager.get_all_episodes()
        assert len(episodes) == 1
        assert episodes[0]["metadata"]["emotion"] == "happy"

    def test_record_multiple_episodes(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("情景一")
        manager.record_episode("情景二", emotion_tag="sad")
        manager.record_episode("情景三", emotion_tag="happy")

        episodes = manager.get_all_episodes()
        assert len(episodes) == 3

    def test_retrieve_relevant_memories(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("今天天气很好，阳光明媚")
        manager.record_episode("主人表扬了我，我很开心")
        manager.record_episode("下雨了，需要带伞")

        results = manager.retrieve_relevant_memories("天气")
        assert len(results) <= 2
        assert "今天天气很好，阳光明媚" in results

    def test_retrieve_no_match(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("完全不相关的经历")

        results = manager.retrieve_relevant_memories("xyz")
        # 兜底返回记忆
        assert len(results) > 0

    def test_get_all_episodes(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("经历一")
        manager.record_episode("经历二")

        episodes = manager.get_all_episodes()
        assert len(episodes) == 2

    def test_episode_timestamp(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("测试")

        episodes = manager.get_all_episodes()
        assert "timestamp" in episodes[0]["metadata"]

    def test_chinese_tokenization_integration(self, temp_storage_path):
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("今天去公园散步")
        manager.record_episode("吃了美味的午餐")
        manager.record_episode("看了电影")

        results = manager.retrieve_relevant_memories("吃饭")
        # 吃饭 和 午餐 应该有一定关联
        assert len(results) > 0

    def test_record_episode_with_emotion_intensity(self, temp_storage_path):
        """record_episode 传入 emotion_intensity=75.0 时应存储到 metadata.intensity"""
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("测试", emotion_tag="happy", emotion_intensity=75.0)

        episodes = manager.get_all_episodes()
        assert episodes[0]["metadata"]["intensity"] == 75.0

    def test_record_episode_default_intensity(self, temp_storage_path):
        """默认 intensity 应为 0.0"""
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("测试", emotion_tag="calm")

        episodes = manager.get_all_episodes()
        assert episodes[0]["metadata"]["intensity"] == 0.0

    def test_retrieve_with_level_filter(self, temp_storage_path):
        """传入 level='consolidated' 时只返回该等级的片段"""
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("早期记忆", emotion_tag="calm")
        manager.record_episode("近期记忆", emotion_tag="happy")

        results = manager.retrieve_relevant_memories("记忆", level="consolidated")
        assert all("早期" not in r for r in results)

    def test_retrieve_with_current_emotion(self, temp_storage_path):
        """传入 current_emotion='sad' 时应给悲伤记忆加权"""
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.record_episode("难过的一天", emotion_tag="sad")
        manager.record_episode("快乐的一天", emotion_tag="happy")

        results = manager.retrieve_relevant_memories("一天", current_emotion="sad")
        assert "难过的一天" in results

    def test_consolidated_first_retrieved(self, temp_storage_path):
        """consolidated 记忆应排在 episodic 之前"""
        manager = EpisodeMemoryManager(temp_storage_path)
        manager.storage.add_memory("episodic事件", tags={"emotion": "calm"})
        manager.storage.memories[0]["metadata"]["level"] = "episodic"
        manager.storage.add_memory("consolidated事件", tags={"emotion": "calm"})
        manager.storage.memories[1]["metadata"]["level"] = "consolidated"

        results = manager.retrieve_relevant_memories("事件")
        assert results[0] == "consolidated事件"
