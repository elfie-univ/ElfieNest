"""NightMemoryConsolidator 单元测试

测试夜间记忆固化系统的失败场景与边界条件。
当前实现存在已知 bug，这些测试用于暴露问题 (TDD RED)。
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from elfie.brain.memory.episode_manager import EpisodeMemoryManager
    from elfie.brain.memory.night_consolidator import NightMemoryConsolidator
except ImportError:
    pytest.skip("旧记忆模块已移除（Task 20），请使用 MemorySystem", allow_module_level=True)


class MockRuntimeSuccess:
    """模拟LLM成功返回固化结果"""
    def ask(self, prompt, energy, task_complexity):
        return "艾菲今天和主人去了公园散步，玩得很开心。\n主人帮艾菲检查了电池电量并充电。"


class MockRuntimeEmpty:
    """模拟LLM返回空字符串"""
    def ask(self, prompt, energy, task_complexity):
        return ""


class MockRuntimeFailure:
    """模拟LLM抛出异常"""
    def ask(self, prompt, energy, task_complexity):
        raise RuntimeError("LLM调用超时")


class TestNightConsolidator:
    """NightMemoryConsolidator 失败测试 (TDD RED)"""

    @pytest.fixture
    def temp_storage_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.remove(temp_path)

    @pytest.fixture
    def manager_with_episodes(self, temp_storage_path):
        """创建一个包含3条情景记忆的EpisodeMemoryManager"""
        mgr = EpisodeMemoryManager(temp_storage_path)
        mgr.record_episode("今天天气很好，去公园散步了", emotion_tag="happy")
        mgr.record_episode("下午吃了美味的冰淇淋", emotion_tag="happy")
        mgr.record_episode("晚上和主人一起看电影", emotion_tag="calm")
        return mgr

    @pytest.fixture
    def manager_with_sad_episodes(self, temp_storage_path):
        """创建一个主导情绪为sad的情景记忆集合"""
        mgr = EpisodeMemoryManager(temp_storage_path)
        mgr.record_episode("今天摔了一跤，膝盖很疼", emotion_tag="sad")
        mgr.record_episode("午餐不好吃，没胃口", emotion_tag="sad")
        mgr.record_episode("下雨了，不能出去玩", emotion_tag="sad")
        return mgr

    def test_consolidator_init(self):
        """NightMemoryConsolidator 接受 EpisodeMemoryManager"""
        mgr = EpisodeMemoryManager()
        consolidator = NightMemoryConsolidator(mgr)
        assert consolidator.mgr is mgr

    def test_consolidator_below_threshold(self, temp_storage_path):
        """少于3条记忆返回"No consolidation needed." """
        mgr = EpisodeMemoryManager(temp_storage_path)
        mgr.record_episode("只有一条记忆")
        consolidator = NightMemoryConsolidator(mgr)
        result = consolidator.run_consolidation(MockRuntimeSuccess())
        assert result == "No consolidation needed."

    def test_consolidator_successful(self, manager_with_episodes):
        """3+记忆且LLM成功时，输出格式正确"""
        consolidator = NightMemoryConsolidator(manager_with_episodes)
        result = consolidator.run_consolidation(MockRuntimeSuccess())
        # 返回值应包含两条非空行
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) == 2
        # 固化后应保留2条新记忆（原3条被清空，写入2条固化结果）
        episodes = manager_with_episodes.get_all_episodes()
        assert len(episodes) == 2
        for ep in episodes:
            assert ep["content"].startswith("【长期固化记忆】")

    def test_consolidator_preserves_memories_on_failure(self, manager_with_episodes):
        """LLM抛异常时原记忆完整保留"""
        original_count = len(manager_with_episodes.get_all_episodes())
        consolidator = NightMemoryConsolidator(manager_with_episodes)
        result = consolidator.run_consolidation(MockRuntimeFailure())
        assert "Error" in result
        # 异常发生在 line 48 (ask)，line 54 未执行，原记忆应保留
        episodes = manager_with_episodes.get_all_episodes()
        assert len(episodes) == original_count

    def test_consolidator_preserves_memories_on_empty_response(self, manager_with_episodes):
        """LLM返回空字符串时原记忆保留

        当前 bug (line 54): self.mgr.storage.memories = [] 无条件清空所有记忆，
        即使 LLM 返回空导致没有写入任何固化结果，原记忆也永久丢失。
        """
        original_count = len(manager_with_episodes.get_all_episodes())
        consolidator = NightMemoryConsolidator(manager_with_episodes)
        consolidator.run_consolidation(MockRuntimeEmpty())
        episodes = manager_with_episodes.get_all_episodes()
        # 期待原记忆保留，但 line 54 bug 导致被清空
        assert len(episodes) == original_count

    def test_consolidator_uses_dominant_emotion(self, manager_with_sad_episodes):
        """巩固结果使用实际情绪而非硬编码"happy"

        当前 bug (line 61): emotion_tag="happy" 硬编码，
        忽略了原始记忆中的真实主导情绪。
        """
        consolidator = NightMemoryConsolidator(manager_with_sad_episodes)
        consolidator.run_consolidation(MockRuntimeSuccess())
        episodes = manager_with_sad_episodes.get_all_episodes()
        for ep in episodes:
            # 原始记忆全是 sad，固化后情绪应保留为 sad
            assert ep["metadata"]["emotion"] == "sad"

    def test_consolidator_marks_consolidated_level(self, manager_with_episodes):
        """巩固后记忆 metadata.level == "consolidated"

        当前缺失标记：record_episode 调用未传递 level 参数，
        固化的新记忆缺少 consolidated 层级标记。
        """
        consolidator = NightMemoryConsolidator(manager_with_episodes)
        consolidator.run_consolidation(MockRuntimeSuccess())
        episodes = manager_with_episodes.get_all_episodes()
        for ep in episodes:
            assert ep["metadata"].get("level") == "consolidated"
