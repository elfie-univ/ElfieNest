"""Token Tracker Tests - T7 实现

测试 token 使用追踪器的核心功能。
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from ai_runtime.usage.token_tracker import TokenTracker, get_token_tracker


class TestTokenTracker:
    """TokenTracker 测试套件"""

    def test_record_accumulates_token_counts_per_provider(self):
        """TokenTracker.record() 应按 provider 累计 token 数"""
        tracker = TokenTracker()
        
        tracker.record("openai", {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        tracker.record("openai", {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300})
        
        summary = tracker.get_tick_summary()
        assert summary["openai"]["prompt_tokens"] == 300
        assert summary["openai"]["completion_tokens"] == 150
        assert summary["openai"]["total_tokens"] == 450

    def test_record_handles_anthropic_format(self):
        """TokenTracker.record() 应处理 Anthropic 格式 (input_tokens/output_tokens)"""
        tracker = TokenTracker()
        
        tracker.record("anthropic", {"input_tokens": 500, "output_tokens": 250})
        
        summary = tracker.get_tick_summary()
        assert summary["anthropic"]["prompt_tokens"] == 500
        assert summary["anthropic"]["completion_tokens"] == 250

    def test_estimate_tokens_chinese_text(self):
        """TokenTracker.estimate_tokens() 应正确估算中文文本"""
        tracker = TokenTracker()
        
        # 8 个中文字 ≈ 12 tokens (8 * 1.5)
        chinese_text = "这是一个测试文本"
        result = tracker.estimate_tokens(chinese_text)
        assert result == 12

    def test_estimate_tokens_english_text(self):
        """TokenTracker.estimate_tokens() 应正确估算英文文本"""
        tracker = TokenTracker()
        
        # 19 个英文字符 ≈ 4 tokens (int(19 / 4))
        english_text = "Hello World Test!!!"
        result = tracker.estimate_tokens(english_text)
        assert result == 4

    def test_get_tick_summary_returns_current_totals(self):
        """TokenTracker.get_tick_summary() 应返回当前累计值"""
        tracker = TokenTracker()
        
        tracker.record("deepseek", {"prompt_tokens": 300, "completion_tokens": 200})
        
        summary = tracker.get_tick_summary()
        assert "deepseek" in summary
        assert summary["deepseek"]["prompt_tokens"] == 300
        assert summary["deepseek"]["completion_tokens"] == 200

    def test_flush_tick_persists_to_file_and_resets_counter(self):
        """TokenTracker.flush_tick() 应持久化到文件并重置计数器"""
        tracker = TokenTracker()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("ai_runtime.usage.token_tracker.get_elfie_home", return_value=Path(tmpdir)):
                tracker.record("openai", {"prompt_tokens": 100, "completion_tokens": 50})
                
                tracker.flush_tick("tick_001")
                
                # 验证计数器已重置
                assert tracker.get_tick_summary() == {}
                
                # 验证文件已写入
                usage_file = Path(tmpdir) / "token_usage.jsonl"
                assert usage_file.exists()
                
                with open(usage_file, "r", encoding="utf-8") as f:
                    record = json.loads(f.readline())
                    assert record["tick_id"] == "tick_001"
                    assert "openai" in record["usage"]

    def test_thread_safety_concurrent_record_calls(self):
        """TokenTracker.record() 应线程安全，并发调用不丢数据"""
        tracker = TokenTracker()
        num_threads = 10
        calls_per_thread = 100
        
        def worker():
            for _ in range(calls_per_thread):
                tracker.record("openai", {"prompt_tokens": 1, "completion_tokens": 1})
        
        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        summary = tracker.get_tick_summary()
        assert summary["openai"]["prompt_tokens"] == num_threads * calls_per_thread
        assert summary["openai"]["completion_tokens"] == num_threads * calls_per_thread

    def test_record_with_empty_usage_dict_is_noop(self):
        """TokenTracker.record() 使用空 usage 字典应为无操作"""
        tracker = TokenTracker()
        
        tracker.record("openai", {})
        tracker.record("anthropic", None)
        
        assert tracker.get_tick_summary() == {}

    def test_multiple_providers_tracked_independently(self):
        """TokenTracker 应独立追踪多个 provider"""
        tracker = TokenTracker()
        
        tracker.record("openai", {"prompt_tokens": 100, "completion_tokens": 50})
        tracker.record("anthropic", {"input_tokens": 200, "output_tokens": 100})
        tracker.record("deepseek", {"prompt_tokens": 300, "completion_tokens": 150})
        
        summary = tracker.get_tick_summary()
        assert len(summary) == 3
        assert summary["openai"]["prompt_tokens"] == 100
        assert summary["anthropic"]["prompt_tokens"] == 200
        assert summary["deepseek"]["prompt_tokens"] == 300


class TestConsumeEnergyByActionTokenBased:
    """consume_energy_by_action() token-based 消耗测试"""

    @pytest.fixture
    def default_config(self):
        return {
            "limits": {
                "energy": {
                    "max_value": 100.0,
                    "initial_value": 100.0,
                    "depletion_per_remote_chat": 2.5,
                    "depletion_per_local_chat": 0.5,
                },
                "fatigue": {
                    "max_value": 100.0,
                    "initial_value": 0.0,
                },
            }
        }

    def test_consume_energy_with_token_count_higher_cost(self, default_config):
        """consume_energy_by_action(token_count=1000, cost_tier=3) 应计算更高消耗"""
        from elfie.brain.energy.energy import HypothalamusEnergy
        
        energy = HypothalamusEnergy(default_config)
        initial = energy.energy
        
        # token_count=1000, cost_tier=3
        # cost = 2.5 * (1000/1000) * (3/2) = 3.75
        energy.consume_energy_by_action(token_count=1000, cost_tier=3)
        
        assert energy.energy == pytest.approx(initial - 3.75, rel=1e-5)

    def test_consume_energy_backward_compat_remote(self, default_config):
        """consume_energy_by_action(is_remote=True) 应仍正常工作（向后兼容）"""
        from elfie.brain.energy.energy import HypothalamusEnergy
        
        energy = HypothalamusEnergy(default_config)
        initial = energy.energy
        
        energy.consume_energy_by_action(is_remote=True)
        
        assert energy.energy == pytest.approx(initial - 2.5, rel=1e-5)

    def test_consume_energy_backward_compat_local(self, default_config):
        """consume_energy_by_action(is_remote=False) 应仍正常工作（向后兼容）"""
        from elfie.brain.energy.energy import HypothalamusEnergy
        
        energy = HypothalamusEnergy(default_config)
        initial = energy.energy
        
        energy.consume_energy_by_action(is_remote=False)
        
        assert energy.energy == pytest.approx(initial - 0.5, rel=1e-5)

    def test_consume_energy_token_count_zero_uses_legacy(self, default_config):
        """consume_energy_by_action(is_remote=True, token_count=0) 应使用旧方式"""
        from elfie.brain.energy.energy import HypothalamusEnergy
        
        energy = HypothalamusEnergy(default_config)
        initial = energy.energy
        
        # 当 token_count=0 时，使用 is_remote 参数
        energy.consume_energy_by_action(is_remote=True, token_count=0)
        
        assert energy.energy == pytest.approx(initial - 2.5, rel=1e-5)

    def test_consume_energy_different_cost_tiers(self, default_config):
        """不同 cost_tier 应产生不同消耗"""
        from elfie.brain.energy.energy import HypothalamusEnergy
        
        energy1 = HypothalamusEnergy(default_config)
        energy2 = HypothalamusEnergy(default_config)
        energy3 = HypothalamusEnergy(default_config)
        
        # cost_tier=1: cost = 2.5 * (500/1000) * (1/2) = 0.625
        energy1.consume_energy_by_action(token_count=500, cost_tier=1)
        
        # cost_tier=2: cost = 2.5 * (500/1000) * (2/2) = 1.25
        energy2.consume_energy_by_action(token_count=500, cost_tier=2)
        
        # cost_tier=3: cost = 2.5 * (500/1000) * (3/2) = 1.875
        energy3.consume_energy_by_action(token_count=500, cost_tier=3)
        
        assert energy1.energy > energy2.energy > energy3.energy


class TestGetTokenTrackerSingleton:
    """get_token_tracker() 单例测试"""

    def test_singleton_returns_same_instance(self):
        """get_token_tracker() 应返回全局单例"""
        tracker1 = get_token_tracker()
        tracker2 = get_token_tracker()
        
        assert tracker1 is tracker2

    def test_singleton_thread_safety(self):
        """get_token_tracker() 应线程安全"""
        trackers = []
        
        def worker():
            trackers.append(get_token_tracker())
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 所有 tracker 应该是同一个实例
        assert all(t is trackers[0] for t in trackers)
