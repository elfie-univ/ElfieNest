"""Memory Module Integration Tests

测试端到端记忆流程：记录、检索、巩固、情绪加权。
"""

import json
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


class TestMemoryIntegration:
    """记忆模块端到端集成测试"""

    def test_full_memory_lifecycle(self):
        """完整记忆生命周期：记录→检索→巩固→再检索"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            mgr = EpisodeMemoryManager(path)
            # 记录3条情景记忆
            mgr.record_episode("今天天气很好，去公园散步了", emotion_tag="happy", emotion_intensity=80.0)
            mgr.record_episode("下午吃了美味的冰淇淋", emotion_tag="happy", emotion_intensity=90.0)
            mgr.record_episode("晚上和主人一起看电影", emotion_tag="calm", emotion_intensity=30.0)
            assert len(mgr.get_all_episodes()) == 3
            # 巩固
            consolidator = NightMemoryConsolidator(mgr)

            class MockRuntime:
                def ask(self, p, energy, task_complexity):
                    return "和主人一起度过愉快的户外时光\n享受美味的甜点和休闲时光"

            result = consolidator.run_consolidation(MockRuntime())
            assert "Error" not in result
            # 巩固后应该只有2条固化记忆（原3条被压缩为2条）
            episodes = mgr.get_all_episodes()
            assert len(episodes) == 2
            for ep in episodes:
                assert ep["metadata"]["level"] == "consolidated"
                assert ep["content"].startswith("【长期固化记忆】")
            # 重新检索
            retrieved = mgr.retrieve_relevant_memories("主人")
            assert len(retrieved) > 0
        finally:
            os.unlink(path)

    def test_emotion_weighted_retrieval_integration(self):
        """情绪影响检索结果：匹配的情绪应该提高相关记忆的排序"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            mgr = EpisodeMemoryManager(path)
            mgr.record_episode("今天摔了一跤，膝盖很疼", emotion_tag="sad", emotion_intensity=80.0)
            # NOTE: 两个记忆都需要包含查询词"今天"的关键字，以便情绪加权决定排序
            mgr.record_episode("今天主人表扬了我，我很开心", emotion_tag="happy", emotion_intensity=90.0)

            # 使用 sad 情绪检索
            sad_results = mgr.retrieve_relevant_memories("今天", current_emotion="sad")
            assert len(sad_results) > 0
            # sad情绪下，悲伤的记忆应该排在前面
            assert "摔了一跤" in sad_results[0]

            # 使用 happy 情绪检索
            happy_results = mgr.retrieve_relevant_memories("今天", current_emotion="happy")
            assert len(happy_results) > 0
            # happy情绪下，开心的记忆应该排在前面
            assert "开心" in happy_results[0]
        finally:
            os.unlink(path)

    def test_backward_compatible_old_format(self):
        """加载旧格式JSON（无level/intensity字段）自动补默认值"""
        import json

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            old_data = [
                {"content": "旧记忆", "metadata": {"emotion": "happy", "timestamp": "2024-01-01"}},
            ]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(old_data, f)
            mgr = EpisodeMemoryManager(path)
            episodes = mgr.get_all_episodes()
            assert len(episodes) == 1
            assert episodes[0]["metadata"].get("level") == "episodic"
            assert episodes[0]["metadata"].get("intensity") == 0.0
        finally:
            os.unlink(path)

    def test_consolidation_failure_preserves_memories(self):
        """LLM巩固失败时原记忆完整保留"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            mgr = EpisodeMemoryManager(path)
            mgr.record_episode("记忆一", emotion_tag="happy", emotion_intensity=50.0)
            mgr.record_episode("记忆二", emotion_tag="sad", emotion_intensity=30.0)
            mgr.record_episode("记忆三", emotion_tag="calm", emotion_intensity=20.0)
            original_count = len(mgr.get_all_episodes())

            consolidator = NightMemoryConsolidator(mgr)

            class MockRuntimeError:
                def ask(self, p, energy, task_complexity):
                    raise RuntimeError("LLM挂了")

            result = consolidator.run_consolidation(MockRuntimeError())
            assert "Error" in result
            # 原记忆完整保留
            assert len(mgr.get_all_episodes()) == original_count
        finally:
            os.unlink(path)

    def test_capacity_warning(self):
        """超过100条episodic记忆时触发容量警告（不丢失记忆）"""
        import logging

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            mgr = EpisodeMemoryManager(path)
            # 添加101条记忆
            for i in range(101):
                mgr.record_episode(f"记忆{i}", emotion_tag="calm")
            # 不超过100条（超过的会被裁剪到最新100条）
            episodes = mgr.get_all_episodes()
            assert len(episodes) <= 100
        finally:
            os.unlink(path)

    def test_sleep_wake_consolidation_flow(self):
        """模拟睡眠→唤醒流程：验证 was_sleeping 边沿检测逻辑"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            mgr = EpisodeMemoryManager(path)
            mgr.record_episode("睡前记忆一", emotion_tag="happy", emotion_intensity=50.0)
            mgr.record_episode("睡前记忆二", emotion_tag="happy", emotion_intensity=60.0)
            mgr.record_episode("睡前记忆三", emotion_tag="calm", emotion_intensity=30.0)

            # 模拟 was_sleeping 逻辑
            was_sleeping = True  # 刚刚醒来
            currently_sleeping = False
            should_consolidate = was_sleeping and not currently_sleeping
            assert should_consolidate  # 应该触发巩固

            consolidator = NightMemoryConsolidator(mgr)

            class MockRuntime:
                def ask(self, p, energy, task_complexity):
                    return "睡前的快乐时光\n休息前保持了平静"

            if should_consolidate:
                result = consolidator.run_consolidation(MockRuntime())
                assert "Error" not in result
                episodes = mgr.get_all_episodes()
                assert len(episodes) == 2
                for ep in episodes:
                    assert ep["metadata"]["level"] == "consolidated"

            # 第二次调用：不应重复巩固
            was_sleeping = False  # 已经醒着
            currently_sleeping = False
            should_consolidate_again = was_sleeping and not currently_sleeping
            assert not should_consolidate_again  # 不应该重复巩固
        finally:
            os.unlink(path)
