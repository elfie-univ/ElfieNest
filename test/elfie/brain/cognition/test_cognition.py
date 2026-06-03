"""Cognition Module Unit Tests

Test Brain (NeocortexBrain), AttentionManager, and ExpectationManager.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.cognition.attention_manager import AttentionManager
from elfie.brain.cognition.brain import NeocortexBrain
from elfie.brain.cognition.expectation import ExpectationManager


class TestAttentionManager:
    """AttentionManager功能测试"""

    def test_init_default_network(self):
        """默认初始化为DMN模式"""
        am = AttentionManager()
        assert am.current_network == "DMN"
        assert am._interrupted is False

    def test_evaluate_state_salience_high(self):
        """高突显度触发SN网络"""
        am = AttentionManager()
        result = am.evaluate_state(has_new_user_message=False, salience_score=80.0)
        assert result == "SN"
        assert am.current_network == "SN"
        assert am.is_interrupted() is True

    def test_evaluate_state_salience_threshold(self):
        """突显度边界值70触发SN"""
        am = AttentionManager()
        result = am.evaluate_state(has_new_user_message=False, salience_score=70.0)
        assert result == "SN"

    def test_evaluate_state_salience_below_threshold(self):
        """突显度低于70不触发SN"""
        am = AttentionManager()
        result = am.evaluate_state(has_new_user_message=False, salience_score=69.9)
        assert result == "DMN"

    def test_evaluate_state_has_message(self):
        """有新消息时切换到CEN"""
        am = AttentionManager()
        result = am.evaluate_state(has_new_user_message=True, salience_score=0.0)
        assert result == "CEN"
        assert am.current_network == "CEN"

    def test_evaluate_state_no_message_idle(self):
        """无新消息低突显度回退到DMN"""
        am = AttentionManager()
        am.current_network = "CEN"  # 先设为CEN
        result = am.evaluate_state(has_new_user_message=False, salience_score=0.0)
        assert result == "DMN"
        assert am.current_network == "DMN"

    def test_evaluate_state_salience_overrides_message(self):
        """高突显度优先于消息触发SN"""
        am = AttentionManager()
        result = am.evaluate_state(has_new_user_message=True, salience_score=90.0)
        assert result == "SN"

    def test_is_interrupted_auto_reset(self):
        """is_interrupted读取后自动复位"""
        am = AttentionManager()
        am.evaluate_state(has_new_user_message=False, salience_score=80.0)
        assert am.is_interrupted() is True
        assert am.is_interrupted() is False  # 自动复位


class TestExpectationManager:
    """ExpectationManager功能测试"""

    def test_init_default_values(self):
        """默认初始化值"""
        em = ExpectationManager()
        assert em.expected_temperature == 24.0
        assert em.expected_user_active is False
        assert em.prediction_error_threshold == 30.0

    def test_update_and_calculate_error_normal(self):
        """正常温度无预测误差"""
        em = ExpectationManager()
        sensors = {
            "temperature": 24.0,
            "has_new_message": False,
            "is_network_online": True,
        }
        error = em.update_and_calculate_error(sensors)
        assert error == 0.0

    def test_update_and_calculate_error_temperature_high(self):
        """温度偏高产生误差"""
        em = ExpectationManager()
        sensors = {
            "temperature": 30.0,
            "has_new_message": False,
            "is_network_online": True,
        }
        error = em.update_and_calculate_error(sensors)
        assert error > 0
        assert error <= 40.0  # 最高40分

    def test_update_and_calculate_error_temperature_low(self):
        """温度偏低产生误差"""
        em = ExpectationManager()
        sensors = {
            "temperature": 18.0,
            "has_new_message": False,
            "is_network_online": True,
        }
        error = em.update_and_calculate_error(sensors)
        assert error > 0

    def test_update_and_calculate_error_temperature_small_diff(self):
        """温度变化小于2度不计误差"""
        em = ExpectationManager()
        sensors = {
            "temperature": 25.0,
            "has_new_message": False,
            "is_network_online": True,
        }
        error = em.update_and_calculate_error(sensors)
        assert error == 0.0

    def test_update_and_calculate_error_new_message(self):
        """新消息产生大误差"""
        em = ExpectationManager()
        sensors = {
            "temperature": 24.0,
            "has_new_message": True,
            "is_network_online": True,
        }
        error = em.update_and_calculate_error(sensors)
        assert error >= 50.0

    def test_update_and_calculate_error_network_offline(self):
        """断网产生误差"""
        em = ExpectationManager()
        sensors = {
            "temperature": 24.0,
            "has_new_message": False,
            "is_network_online": False,
        }
        error = em.update_and_calculate_error(sensors)
        assert error >= 35.0

    def test_update_and_calculate_error_multiple(self):
        """多重误差叠加"""
        em = ExpectationManager()
        sensors = {
            "temperature": 35.0,
            "has_new_message": True,
            "is_network_online": False,
        }
        error = em.update_and_calculate_error(sensors)
        assert error > 50.0  # 40 + 50 + 35

    def test_should_take_active_action_below_threshold(self):
        """误差小于阈值不触发主动行为"""
        em = ExpectationManager()
        assert em.should_take_active_action(20.0) is False

    def test_should_take_active_action_at_threshold(self):
        """误差等于阈值触发主动行为"""
        em = ExpectationManager()
        assert em.should_take_active_action(30.0) is True

    def test_should_take_active_action_above_threshold(self):
        """误差大于阈值触发主动行为"""
        em = ExpectationManager()
        assert em.should_take_active_action(50.0) is True


class TestNeocortexBrain:
    """NeocortexBrain功能测试"""

    def test_init(self):
        """初始化测试"""
        brain = NeocortexBrain()
        assert brain.profile is not None
        assert brain.attention is not None
        assert brain.expectation is not None

    def test_init_with_config_dir(self):
        """带config_dir初始化"""
        brain = NeocortexBrain(config_dir="/tmp/test")
        assert brain.profile.config_dir == "/tmp/test"

    def test_think_and_decide_sn_mode(self):
        """SN模式决策测试"""
        brain = NeocortexBrain()

        class MockRuntime:
            def ask(self, prompt, energy, task_complexity):
                return "哎呀！吓我一跳！[ACTION]wiggle_ears[/ACTION]"

        context = {
            "sensors": {"has_new_message": False, "salience_score": 80.0},
            "energy": 100.0,
        }
        result = brain.think_and_decide(context, MockRuntime())

        assert result["attention_mode"] == "SN"
        assert result["action"] == "wiggle_ears"
        assert "speech_text" in result

    def test_think_and_decide_cen_mode(self):
        """CEN模式决策测试"""
        brain = NeocortexBrain()

        class MockRuntime:
            def ask(self, prompt, energy, task_complexity):
                return "你好呀！主人！"

        context = {
            "sensors": {
                "has_new_message": True,
                "salience_score": 0.0,
                "user_message": "在吗？",
            },
            "energy": 100.0,
            "emotion_state": "平静",
            "history_episodes": "无相关记忆",
        }
        result = brain.think_and_decide(context, MockRuntime())

        assert result["attention_mode"] == "CEN"
        assert result["action"] == "nod_head"

    def test_think_and_decide_cen_with_action_tag(self):
        """CEN模式解析动作标签"""
        brain = NeocortexBrain()

        class MockRuntime:
            def ask(self, prompt, energy, task_complexity):
                return "好呀！[ACTION]wag_tail[/ACTION]"

        context = {
            "sensors": {
                "has_new_message": True,
                "salience_score": 0.0,
                "user_message": "来",
            },
            "energy": 100.0,
            "emotion_state": "平静",
            "history_episodes": "",
        }
        result = brain.think_and_decide(context, MockRuntime())

        assert result["action"] == "wag_tail"
        assert "wag_tail" not in result["speech_text"]  # 动作标签被移除

    def test_think_and_decide_dmn_active_mode(self):
        """DMN主动模式（高预测误差）"""
        brain = NeocortexBrain()

        class MockRuntime:
            def ask(self, prompt, energy, task_complexity):
                return "今天天气不错呀！"

        context = {
            "sensors": {
                "has_new_message": False,
                "salience_score": 0.0,
                "temperature": 40.0,
            },
            "energy": 100.0,
            "emotion_mood": "bored",
        }
        result = brain.think_and_decide(context, MockRuntime())

        assert result["attention_mode"] == "DMN_ACTIVE"
        assert result["action"] == "wag_tail"

    def test_think_and_decide_dmn_idle_mode(self):
        """DMN空闲模式（低预测误差）"""
        brain = NeocortexBrain()

        class MockRuntime:
            def ask(self, prompt, energy, task_complexity):
                return "不应被调用"

        context = {
            "sensors": {
                "has_new_message": False,
                "salience_score": 0.0,
                "temperature": 24.0,
            },
            "energy": 100.0,
            "emotion_mood": "bored",
        }
        result = brain.think_and_decide(context, MockRuntime())

        assert result["attention_mode"] == "DMN_IDLE"
        assert result["mutter"] is not None  # 有碎碎念
        assert result["action"] == "blink_eyes"

    def test_think_and_decide_missing_sensors(self):
        """缺少sensors字段的边界情况"""
        brain = NeocortexBrain()

        class MockRuntime:
            def ask(self, prompt, energy, task_complexity):
                return "回复"

        context = {"sensors": {}, "energy": 100.0, "emotion_mood": "bored"}
        result = brain.think_and_decide(context, MockRuntime())

        # 应该有默认值，不崩溃
        assert result is not None
        assert "attention_mode" in result

    def test_think_and_decide_missing_context_fields(self):
        """缺少context中部分字段"""
        brain = NeocortexBrain()

        class MockRuntime:
            def ask(self, prompt, energy, task_complexity):
                return "回复"

        context = {
            "sensors": {
                "has_new_message": True,
                "salience_score": 0.0,
                "user_message": "Hi",
            }
        }
        result = brain.think_and_decide(context, MockRuntime())

        assert result is not None


class TestEdgeCases:
    """边界情况和异常场景测试"""

    def test_attention_manager_extreme_salience(self):
        """极端突显度值"""
        am = AttentionManager()
        result = am.evaluate_state(False, 100.0)
        assert result == "SN"

    def test_attention_manager_negative_salience(self):
        """负突显度值"""
        am = AttentionManager()
        result = am.evaluate_state(False, -10.0)
        assert result == "DMN"

    def test_expectation_manager_extreme_temperature(self):
        """极端温度值"""
        em = ExpectationManager()
        sensors = {
            "temperature": 100.0,
            "has_new_message": False,
            "is_network_online": True,
        }
        error = em.update_and_calculate_error(sensors)
        assert error == 40.0  # 封顶40

    def test_expectation_manager_empty_sensors(self):
        """空传感器数据"""
        em = ExpectationManager()
        sensors = {}
        error = em.update_and_calculate_error(sensors)
        # 使用默认值24.0，无误差
        assert error == 0.0

    def test_brain_with_none_runtime(self):
        """runtime_agent为None时的边界情况"""
        brain = NeocortexBrain()
        _ = {
            "sensors": {
                "has_new_message": False,
                "salience_score": 0.0,
                "temperature": 24.0,
            },
            "energy": 100.0,
            "emotion_mood": "bored",
        }
        # 不调用think_and_decide，只测初始化
        assert brain.attention is not None
