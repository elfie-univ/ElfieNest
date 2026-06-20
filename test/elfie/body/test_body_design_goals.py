"""身体层设计目标验证测试

验证关节安全限位、脑干反射避险/抚慰、信号过滤等设计目标。
"""

import pytest

from elfie import ElfieIndividual
from elfie.body.anatomy.biped import BipedAnatomy
from elfie.interface.signal_filter import SensoryDamSignalFilter


class MockRuntimeAgent:
    """Mock LLM runtime agent，仅用于构造签名（反射路径不会调用）"""
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
# 关节安全限制测试
# =============================================================================

class TestJointSafetyLimits:
    """验证数字孪生关节的旋转弧度安全限位"""

    def test_joint_above_max_clamped(self):
        """head_yaw最大1.57，set_angle(3.14)返回1.57（被截断）"""
        anatomy = BipedAnatomy()

        actual = anatomy.joints["head_yaw"].set_angle(3.14)

        assert actual == 1.57, (
            f"head_yaw 超出上限 1.57 应被截断，实际返回 {actual}"
        )

    def test_joint_below_min_clamped(self):
        """left_knee最小0.0，set_angle(-1.0)返回0.0（被截断）"""
        anatomy = BipedAnatomy()

        actual = anatomy.joints["left_knee"].set_angle(-1.0)

        assert actual == 0.0, (
            f"left_knee 低于下限 0.0 应被截断到 0.0，实际返回 {actual}"
        )


# =============================================================================
# 脑干反射避险测试
# =============================================================================

class TestBrainstemShockReflex:
    """验证剧烈撞击触发的脑干自主避险反射"""

    def test_brainstem_shock_reflex(self):
        """构造ElfieIndividual(quadruped)，传入impact_force=25, impact_direction="right"
        →perceive_and_respond返回action="reflex_avoidance"，包含"痛"，fear > 20"""
        elfie = ElfieIndividual(anatomy_type="quadruped")

        sensor_data = {
            "has_new_message": False,
            "impact_force": 25.0,
            "impact_direction": "right",
            "gentle_stroke": 0.0,
        }

        # 反射路径不调用 runtime_agent，传入 None 安全
        response = elfie.perceive_and_respond(sensor_data, None)

        assert response["action"] == "reflex_avoidance", (
            f"撞击反射应返回 reflex_avoidance，实际为 {response['action']}"
        )
        assert "痛" in response["speech"], (
            f"反射响应应包含'痛'字，实际为: {response['speech']}"
        )

        # 验证杏仁核情绪被扰动：fear 应 > 20（baseline=10 + anxiety:25 = 35）
        fear = elfie.amygdala.get_emotion_value("fear")
        assert fear > 20.0, (
            f"撞击后 fear 应 > 20，实际为 {fear:.1f}"
        )


# =============================================================================
# 脑干反射抚慰测试
# =============================================================================

class TestBrainstemStrokeReflex:
    """验证温柔抚摸触发的脑干舒适反射"""

    def test_brainstem_stroke_reflex(self):
        """构造ElfieIndividual(quadruped)，传入gentle_stroke=1.2
        →perceive_and_respond返回action="reflex_soothing"，包含"舒服"或"呼噜"，happiness > 50"""
        elfie = ElfieIndividual(anatomy_type="quadruped")

        sensor_data = {
            "has_new_message": False,
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.2,
        }

        response = elfie.perceive_and_respond(sensor_data, None)

        assert response["action"] == "reflex_soothing", (
            f"抚摸反射应返回 reflex_soothing，实际为 {response['action']}"
        )

        speech = response["speech"]
        has_comfort_keyword = "舒服" in speech or "呼噜" in speech
        assert has_comfort_keyword, (
            f"反射响应应包含'舒服'或'呼噜'，实际为: {speech}"
        )

        # 验证幸福感提升：happiness baseline=50 + 15 = 65 > 50
        happiness = elfie.amygdala.get_emotion_value("happiness")
        assert happiness > 50.0, (
            f"抚摸后 happiness 应 > 50，实际为 {happiness:.1f}"
        )


# =============================================================================
# 信号过滤测试
# =============================================================================

class TestSignalFilter:
    """验证感知大坝对重复信号的过滤"""

    def test_signal_filter_blocks_no_change(self):
        """构造连续相同输入→signal_filter.filter_noise第二次相同输入返回False（被过滤）"""
        flt = SensoryDamSignalFilter()

        # 首次输入（温度 24.0）：last_temperature 为 None，应返回 True
        first = flt.filter_noise({"temperature": 24.0})
        assert first is True, "首次输入相同温度应返回 True（初始化）"

        # 第二次相同输入（温度 24.0）：diff=0 < 0.5，应被过滤
        second = flt.filter_noise({"temperature": 24.0})
        assert second is False, "连续相同温度输入应被过滤返回 False"
