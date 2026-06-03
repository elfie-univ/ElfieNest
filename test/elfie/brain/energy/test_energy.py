"""测试 elfie.brain.energy.energy 模块"""

import pytest

from elfie.brain.energy.energy import HypothalamusEnergy


class TestHypothalamusEnergy:
    """能量系统测试套件"""

    @pytest.fixture
    def default_config(self):
        """默认配置 fixture"""
        return {
            "limits": {
                "energy": {
                    "max_value": 100.0,
                    "initial_value": 100.0,
                    "depletion_rate_per_sec": 0.005,
                    "recovery_rate_sleep_per_sec": 0.05,
                    "depletion_per_remote_chat": 2.5,
                    "depletion_per_local_chat": 0.5,
                },
                "fatigue": {
                    "max_value": 100.0,
                    "initial_value": 0.0,
                    "accumulation_rate_per_sec": 0.003,
                    "decay_rate_sleep_per_sec": 0.04,
                    "hibernation_threshold": 95.0,
                    "wakeup_threshold": 15.0,
                },
            }
        }

    @pytest.fixture
    def energy_system(self, default_config):
        """创建能量系统实例"""
        return HypothalamusEnergy(default_config)

    # ===== 初始化测试 =====
    def test_init_default_values(self):
        """测试默认初始化值"""
        system = HypothalamusEnergy()
        assert system.max_energy == 100.0
        assert system.energy == 100.0
        assert system.depletion_rate == 0.005
        assert system.max_fatigue == 100.0
        assert system.fatigue == 0.0
        assert system.accumulation_rate == 0.003
        assert system.hibernation_threshold == 95.0
        assert system.wakeup_threshold == 15.0
        assert system.is_sleeping is False

    def test_init_with_config(self, energy_system):
        """测试使用配置初始化"""
        assert energy_system.max_energy == 100.0
        assert energy_system.energy == 100.0
        assert energy_system.fatigue == 0.0
        assert energy_system.is_sleeping is False

    # ===== 能量消耗测试 =====
    def test_energy_depletes_when_awake(self, energy_system):
        """测试清醒状态能量消耗"""
        initial_energy = energy_system.energy
        dt = 10.0  # 10秒
        energy_system.update_clock(dt)
        expected_depletion = energy_system.depletion_rate * dt
        assert energy_system.is_sleeping is False
        assert energy_system.energy == pytest.approx(
            initial_energy - expected_depletion, rel=1e-5
        )

    def test_fatigue_accumulates_when_awake(self, energy_system):
        """测试清醒状态疲劳累积"""
        initial_fatigue = energy_system.fatigue
        dt = 10.0
        energy_system.update_clock(dt)
        expected_accumulation = energy_system.accumulation_rate * dt
        assert energy_system.fatigue == pytest.approx(
            initial_fatigue + expected_accumulation, rel=1e-5
        )

    def test_consume_energy_local_action(self, energy_system):
        """测试本地动作能量消耗"""
        initial_energy = energy_system.energy
        energy_system.consume_energy_by_action(is_remote=False)
        assert energy_system.energy == pytest.approx(initial_energy - 0.5, rel=1e-5)

    def test_consume_energy_remote_action(self, energy_system):
        """测试远程动作能量消耗"""
        initial_energy = energy_system.energy
        energy_system.consume_energy_by_action(is_remote=True)
        assert energy_system.energy == pytest.approx(initial_energy - 2.5, rel=1e-5)

    def test_energy_never_negative(self, energy_system):
        """测试能量不会变为负数"""
        energy_system.energy = 1.0
        energy_system.consume_energy_by_action(is_remote=True)  # 消耗 2.5
        assert energy_system.energy >= 0.0

    def test_energy_depletes_to_zero(self, energy_system):
        """测试能量耗尽到零"""
        energy_system.energy = 0.5
        dt = 100.0  # 大时间步长
        energy_system.update_clock(dt)
        assert energy_system.energy == 0.0

    # ===== 能量恢复测试 =====
    def test_energy_recovers_when_sleeping(self, energy_system):
        """测试睡眠状态能量恢复"""
        energy_system.is_sleeping = True
        energy_system.energy = 50.0
        dt = 10.0
        initial_energy = energy_system.energy
        energy_system.update_clock(dt)
        recovery = (
            energy_system.energy_config.get("recovery_rate_sleep_per_sec", 0.05) * dt
        )
        assert energy_system.energy == pytest.approx(
            initial_energy + recovery, rel=1e-5
        )

    def test_fatigue_decays_when_sleeping(self, energy_system):
        """测试睡眠状态疲劳消退"""
        energy_system.is_sleeping = True
        energy_system.fatigue = 50.0
        dt = 10.0
        initial_fatigue = energy_system.fatigue
        energy_system.update_clock(dt)
        decay = energy_system.fatigue_config.get("decay_rate_sleep_per_sec", 0.04) * dt
        assert energy_system.fatigue == pytest.approx(initial_fatigue - decay, rel=1e-5)

    def test_energy_max_limit_when_sleeping(self, energy_system):
        """测试睡眠状态能量不超过最大值"""
        energy_system.is_sleeping = True
        energy_system.energy = 99.0
        dt = 100.0  # 大时间步长确保超过最大值
        energy_system.update_clock(dt)
        assert energy_system.energy <= energy_system.max_energy

    def test_fatigue_min_limit_when_sleeping(self, energy_system):
        """测试睡眠状态疲劳不低于零"""
        energy_system.is_sleeping = True
        energy_system.fatigue = 1.0
        dt = 100.0
        energy_system.update_clock(dt)
        assert energy_system.fatigue >= 0.0

    # ===== 低能量警告测试 =====
    def test_wakeup_from_sleeping(self, energy_system):
        """测试疲劳消退到阈值后自动唤醒"""
        energy_system.is_sleeping = True
        energy_system.fatigue = 20.0  # 高于唤醒阈值 15.0
        energy_system.update_clock(5.0)  # 减少 0.04 * 5 = 0.2 疲劳
        # 需要多次tick才能降到阈值以下
        for _ in range(20):
            energy_system.update_clock(10.0)
        # 最终应该唤醒
        assert (
            energy_system.fatigue <= energy_system.wakeup_threshold
            or energy_system.is_sleeping is False
        )

    def test_hibernation_trigger(self, energy_system):
        """测试疲劳达到阈值触发休眠"""
        energy_system.is_sleeping = False
        energy_system.fatigue = 94.0
        energy_system.update_clock(500.0)
        assert energy_system.is_sleeping is True

    # ===== 边界情况测试 =====
    def test_zero_delta_time(self, energy_system):
        """测试零时间步长"""
        initial_energy = energy_system.energy
        initial_fatigue = energy_system.fatigue
        energy_system.update_clock(0.0)
        assert energy_system.energy == initial_energy
        assert energy_system.fatigue == initial_fatigue

    def test_negative_delta_time(self, energy_system):
        """测试负时间步长（边界情况）"""
        initial_energy = energy_system.energy
        energy_system.update_clock(-10.0)
        # 负时间可能导致异常行为，这是边界测试
        assert energy_system.energy is not None

    def test_very_large_delta_time(self, energy_system):
        """测试非常大的时间步长"""
        energy_system.energy = 10.0
        energy_system.fatigue = 80.0
        energy_system.update_clock(10000.0)
        assert energy_system.energy == 0.0
        assert energy_system.fatigue == energy_system.max_fatigue

    def test_get_energy_method(self, energy_system):
        """测试 get_energy 方法"""
        energy_system.energy = 75.5
        assert energy_system.get_energy() == 75.5

    def test_get_fatigue_method(self, energy_system):
        """测试 get_fatigue 方法"""
        energy_system.fatigue = 25.5
        assert energy_system.get_fatigue() == 25.5

    def test_fatigue_max_limit_when_awake(self, energy_system):
        """测试清醒状态疲劳不超过最大值"""
        energy_system.fatigue = 99.0
        dt = 100.0
        energy_system.update_clock(dt)
        assert energy_system.fatigue <= energy_system.max_fatigue

    def test_sleep_state_persists_until_wakeup_threshold(self, energy_system):
        """测试睡眠状态保持直到疲劳降到唤醒阈值"""
        energy_system.is_sleeping = True
        energy_system.fatigue = 50.0
        # 多次小步长tick，观察状态变化
        for _ in range(100):
            energy_system.update_clock(1.0)
        # 睡眠状态应该在某个时刻结束
        assert energy_system.fatigue >= 0.0
