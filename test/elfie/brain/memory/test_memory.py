"""Memory Module Unit Tests

Test EpisodeMemoryManager and TinyVectorStorage for episodic memory management.
"""

import pytest
import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.memory.episode_manager import EpisodeMemoryManager
from elfie.brain.memory.vector_storage import TinyVectorStorage


class TestTinyVectorStorage:

    @pytest.fixture
    def temp_storage_path(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
        test_data = [
            {"content": "test memory", "metadata": {"emotion": "happy"}}
        ]
        with open(temp_storage_path, 'w', encoding='utf-8') as f:
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
            "主人表扬了我",
            tags={"emotion": "happy", "location": "home"}
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
        with open(temp_storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data) == 1


class TestEpisodeMemoryManager:

    @pytest.fixture
    def temp_storage_path(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
