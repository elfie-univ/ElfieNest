"""能量系统设计目标验证测试

验证睡眠熔断、唤醒恢复、情绪-能量交互等设计目标。
"""

import pytest

from elfie import Elfie
from elfie.brain.energy.energy import HypothalamusEnergy


class MockRuntimeAgent:
    """Mock LLM runtime agent，仅用于构造签名"""
    class MockConfig:
        remote_api_key = ""
        providers = {
            "deepseek": {"api_key": "", "api_base": ""},
            "openai": {"api_key": "", "api_base": ""},
            "gemini": {"api_key": "", "api_base": ""},
            "qwen": {"api_key": "", "api_base": ""},
            "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
        }
    config = MockConfig()
    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        return ""


# =============================================================================
# 睡眠熔断测试
# =============================================================================

class TestHibernationFuse:
    """验证疲劳度达到阈值时的自动休眠熔断机制"""

    def test_hibernation_trigger(self):
        """疲劳拉到95→is_sleeping应变为True"""
        energy = HypothalamusEnergy()
        energy.is_sleeping = False
        energy.fatigue = 95.0

        # 调用 update_clock 触发检查（即使 dt=0，fatigue >= threshold 也应触发休眠）
        energy.update_clock(0.0)

        assert energy.is_sleeping is True, (
            f"疲劳度 95.0 >= 休眠阈值 {energy.hibernation_threshold}，应触发休眠"
        )

    def test_sleep_blocks_perception(self):
        """is_sleeping=True时，Elfie.perceive_and_respond
        返回的dict包含"sleeping"或success=False的睡眠相关原因"""
        elfie = Elfie()
        # 直接设置睡眠状态（绕过疲劳累积过程）
        elfie.hypothalamus.is_sleeping = True

        result = elfie.perceive_and_respond(
            {"has_new_message": True, "user_message": "hello"},
            MockRuntimeAgent(),
        )

        assert result.get("success") is False, "睡眠时应返回 success=False"
        reason = result.get("reason", "")
        assert "sleeping" in reason, f"原因应包含 sleeping，实际为: {reason}"

    def test_hibernation_threshold_boundary(self):
        """疲劳恰好95.0→触发睡眠（边界值测试）"""
        energy = HypothalamusEnergy()
        energy.is_sleeping = False
        energy.fatigue = 95.0

        energy.update_clock(0.0)

        assert energy.is_sleeping is True, (
            "边界值 95.0 应触发休眠熔断"
        )


# =============================================================================
# 唤醒恢复测试
# =============================================================================

class TestWakeupRecovery:
    """验证疲劳消退后自动唤醒及能量恢复"""

    def test_wakeup_when_fatigue_low(self):
        """睡眠中疲劳降到15以下→is_sleeping变为False"""
        energy = HypothalamusEnergy()
        energy.is_sleeping = True
        energy.fatigue = 20.0  # 初始略高于唤醒阈值 15.0

        # decay_rate_sleep_per_sec = 0.04
        # 需要从 20 降到 15 以下： 20 - 0.04 * dt < 15 → dt > 125
        energy.update_clock(200.0)

        assert energy.is_sleeping is False, (
            f"疲劳 {energy.fatigue:.1f} <= 唤醒阈值 {energy.wakeup_threshold}，应唤醒"
        )
        assert energy.fatigue <= energy.wakeup_threshold

    def test_sleep_recovers_energy_and_reduces_fatigue(self):
        """睡眠状态下update_clock→energy应增加，fatigue应减少"""
        energy = HypothalamusEnergy()
        energy.is_sleeping = True
        energy.energy = 50.0
        energy.fatigue = 50.0

        before_energy = energy.energy
        before_fatigue = energy.fatigue

        energy.update_clock(10.0)  # 睡眠 10 秒

        assert energy.energy > before_energy, (
            f"睡眠后能量应增加：{before_energy} -> {energy.energy}"
        )
        assert energy.fatigue < before_fatigue, (
            f"睡眠后疲劳应减少：{before_fatigue} -> {energy.fatigue}"
        )


# =============================================================================
# 情绪-能量交互测试
# =============================================================================

class TestEmotionEnergyInteraction:
    """验证 tick() 同时驱动能量消耗和情绪衰减"""

    def test_tick_with_energy_still_decays_emotion(self):
        """构造Elfie，先注入fear=80，然后tick(dt=10)，
        fear应有衰减（验证tick同时驱动能量和情绪衰减）"""
        elfie = Elfie()

        # 注入 fear：baseline=10，加 70 到 80
        elfie.amygdala.update_emotion("fear", 70)
        assert elfie.amygdala.get_emotion_value("fear") == 80.0, (
            "fear 注入后应为 80"
        )

        before_energy = elfie.hypothalamus.get_energy()

        # tick 10 秒：应同时触发能量消耗和情绪衰减
        elfie.tick(10.0)

        after_fear = elfie.amygdala.get_emotion_value("fear")
        after_energy = elfie.hypothalamus.get_energy()

        assert after_fear < 80.0, (
            f"tick 后 fear 应衰减：注入 80.0 -> {after_fear:.2f}"
        )
        assert after_energy < before_energy, (
            f"tick 后能量应减少：{before_energy} -> {after_energy}"
        )
